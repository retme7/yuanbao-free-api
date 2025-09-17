from typing import Dict
from apikey import *
def generate_headers(request: dict, token: str) -> Dict[str, str]:
    print(request)
    # check if request has source
    if 'hy_source' not in request:
        request['hy_source'] = HY_SOURCE
    if 'hy_user' not in request:
        request['hy_user'] = HY_USER
    if 'agent_id' not in request:
        request['agent_id'] = AGENT_ID

    return {
        "Cookie": f"hy_source={request['hy_source']}; hy_user={request['hy_user']}; hy_token={token}",
        "Origin": "https://yuanbao.tencent.com",
        "Referer": f"https://yuanbao.tencent.com/chat/{request['agent_id']}",
        "X-Agentid": request["agent_id"],
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    }
