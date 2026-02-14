
import asyncio
import base64
import hashlib
import logging
import struct
import time
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db, AsyncSessionLocal
from app.crud.site import crud_site
from app.services.chat_service import ChatService
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.schemas.document import VectorRetrieveFilter
from app.core.infra.config import settings
from app.core.wxcrypt import WXBizMsgCrypt

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/wecom-smart-robot")
async def verify_url(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
    site_id: int = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """验证回调 URL (企业微信设置时触发)"""
    site = await crud_site.get(db, id=site_id)
    if not site or not site.bot_config:
        raise HTTPException(status_code=404, detail="Site or config not found")
        
    config = site.bot_config.get("wecomSmartRobot", {})
    if not config or not config.get("enabled"):
        raise HTTPException(status_code=400, detail="WeCom robot not enabled")
        
    token = config.get("token")
    encoding_aes_key = config.get("encodingAesKey")
    
    if not token or not encoding_aes_key:
        raise HTTPException(status_code=400, detail="WeCom robot token or key missing")
        
    crypt = WXBizMsgCrypt(token, encoding_aes_key, "")
    
    try:
        decrypted_echostr = crypt.decrypt(echostr, msg_signature, timestamp, nonce)
        return Response(content=decrypted_echostr)
    except Exception as e:
        logger.error(f"WeCom VerifyURL failed: {e}")
        raise HTTPException(status_code=400, detail="Verification failed")


@router.post("/wecom-smart-robot")
async def handle_message(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    site_id: int = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """处理企业微信消息回调"""
    site = await crud_site.get(db, id=site_id)
    if not site or not site.bot_config:
        return Response(status_code=404)
        
    config = site.bot_config.get("wecomSmartRobot", {})
    if not config or not config.get("enabled"):
        return Response(status_code=403)
        
    token = config.get("token")
    encoding_aes_key = config.get("encodingAesKey")
    
    # 读取 XML 消息体
    body = await request.body()
    try:
        root = ET.fromstring(body)
        encrypt_node = root.find("Encrypt")
        if encrypt_node is None:
            return Response(status_code=400)
        
        encrypt_text = encrypt_node.text
        crypt = WXBizMsgCrypt(token, encoding_aes_key, "")
        xml_content = crypt.decrypt(encrypt_text, msg_signature, timestamp, nonce)
        
        msg_root = ET.fromstring(xml_content)
        msg_type = msg_root.find("MsgType").text
        from_user = msg_root.find("FromUserName").text
        to_user = msg_root.find("ToUserName").text
        
        if msg_type == "text":
            content = msg_root.find("Content").text
            
            # 构造聊天请求
            chat_request = ChatCompletionRequest(
                message=content,
                thread_id=f"wecom-{from_user}",
                user=from_user,
                stream=False,
                filter=VectorRetrieveFilter(site_id=site.id)
            )
            
            # 直接等待处理结果，移除模拟环境下的硬性超时限制
            try:
                logger.info(f"WeCom synchronous AI processed for {from_user}...")
                response = await ChatService.process_chat_request(chat_request, background_tasks)
                reply_text = ""
                if hasattr(response, "choices") and response.choices:
                    reply_text = response.choices[0].message.content or ""
            except Exception as e:
                logger.error(f"WeCom AI error: {e}", exc_info=True)
                reply_text = "抱歉，处理消息时遇到错误。"
            
            # 返回回复消息
            reply_xml = crypt.build_reply_xml(from_user, to_user, reply_text)
            encrypted_reply, signature, ts = crypt.encrypt(reply_xml, nonce)
            
            response_xml = f"""<xml>
<Encrypt><![CDATA[{encrypted_reply}]]></Encrypt>
<MsgSignature><![CDATA[{signature}]]></MsgSignature>
<TimeStamp>{ts}</TimeStamp>
<Nonce><![CDATA[{nonce}]]></Nonce>
</xml>"""
            return Response(content=response_xml, media_type="application/xml")
            
        return Response(content="")
    except Exception as e:
        logger.error(f"WeCom Message handling failed: {e}", exc_info=True)
        return Response(status_code=500)


@router.post(
    "/site-completions",
    response_model=ChatCompletionResponse,
    operation_id="createSiteChatCompletion",
)
async def create_site_chat_completion(
    request: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
    authorization: str = Header(..., description="Bearer <api_key>"),
) -> ChatCompletionResponse | StreamingResponse:
    """
    创建聊天补全 (专用接口，兼容 OpenAI 格式)
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = authorization.replace("Bearer ", "")

    async with AsyncSessionLocal() as db:
        site = await crud_site.get_by_api_token(db, api_token=token)
        if not site:
            raise HTTPException(status_code=401, detail="Invalid API Key")

    # 统一将识别出的 site_id 注入 filter
    if not request.filter:
        request.filter = VectorRetrieveFilter(site_id=site.id)
    else:
        request.filter.site_id = site.id

    return await ChatService.process_chat_request(request, background_tasks)


