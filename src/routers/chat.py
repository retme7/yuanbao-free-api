import logging

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from src.dependencies.auth import get_authorized_headers
from src.schemas.chat import ChatCompletionRequest, YuanBaoChatCompletionRequest
from src.services.chat.completion import create_completion_stream
from src.services.chat.conversation import create_conversation
from src.utils.chat import get_model_info, parse_messages

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    headers: dict = Depends(get_authorized_headers),
):
    try:
        if not request.chat_id:
            request.chat_id = await create_conversation(request.agent_id, headers)
            logging.info(f"Conversation created with chat_id: {request.chat_id}")

        prompt = parse_messages(request.messages)
        model_info = get_model_info(request.model)
        if not model_info:
            raise HTTPException(status_code=400, detail="invalid model")

        chat_request = YuanBaoChatCompletionRequest(
            agent_id=request.agent_id,
            chat_id=request.chat_id,
            prompt=prompt,
            chat_model_id=model_info["model"],
            multimedia=request.multimedia,
            support_functions=model_info.get("support_functions"),
        )

        generator = create_completion_stream(chat_request, headers, request.should_remove_conversation)
        logging.info(f"Streaming chat completion for chat_id: {request.chat_id}")

        if request.stream:
            return EventSourceResponse(generator, media_type="text/event-stream")

        # Non-streaming: aggregate chunks into OpenAI-like ChatCompletion JSON
        import json
        import time
        import uuid

        full_text = ""
        finish_reason = "stop"
        usage = None

        async for chunk in generator:
            print(chunk)
            if chunk == "[DONE]":
                break
            try:
                data = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            choices = data.get("choices", [])
            if not choices:
                continue
            choice0 = choices[0]
            delta = choice0.get("delta", {})
            content_value = delta.get("content", "") if isinstance(delta, dict) else ""

            # If content looks like JSON, attempt to parse meta/text structures
            if isinstance(content_value, str) and content_value.startswith("{"):
                try:
                    inner = json.loads(content_value)
                except json.JSONDecodeError:
                    inner = None
                if isinstance(inner, dict):
                    content_type = inner.get("type")
                    if content_type == "meta":
                        print(inner)
                        token_usage = inner.get("tokenUsageInfo") or {}
                        if token_usage:
                            usage = {
                                "prompt_tokens": token_usage.get("promptTokens"),
                                "completion_tokens": token_usage.get("completionTokens"),
                                "total_tokens": token_usage.get("totalTokens"),
                                "prompt_tokens_details": None,
                                "completion_tokens_details": None,
                            }
                        # do not append meta to message content
                    elif content_type == "text":
                        msg_text = inner.get("msg") or ""
                        full_text += msg_text
                    else:
                        # unknown typed content, ignore
                        pass
                else:
                    # content was a JSON-looking string but couldn't parse; append raw
                    full_text += content_value
            else:
                # Plain text content (preferred path when upstream extractor already flattened)
                if isinstance(content_value, str):
                    full_text += content_value

            if choice0.get("finish_reason"):
                finish_reason = choice0["finish_reason"]

        if usage == None:
            usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        response_body = {
            "id": str(uuid.uuid4()),
            "object": "chat.completion",
            "created": int(time.time()),
            # Expose the external model name requested by client
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_text,
                    },
                    "finish_reason": finish_reason,
                    "logprobs": None,
                }
            ],
            "usage": usage,
            "system_fingerprint": None,
            "service_tier": None,
        }
        return response_body
    except Exception as e:
        logging.error(f"Error in chat_completions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
