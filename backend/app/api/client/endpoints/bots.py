import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.integration.robot.wecom_smart.adapter import WeComBufferManager
from app.core.integration.robot.wecom_smart.crypt import WXBizJsonMsgCrypt
from app.core.integration.robot.wecom_smart.service import WeComSmartService
from app.core.integration.robot.wecom_kefu.service import WeComKefuService
from app.core.integration.robot.wecom_app.service import WeComAppService
from app.core.integration.robot.wecom_kefu.xml_crypt import WXBizXmlMsgCrypt
from app.crud.site import crud_site
from app.db.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_wecom_smart_bot_context(
    request: Request, site_id: int = Query(...), db: AsyncSession = Depends(get_db)
):
    """获取企业微信智能机器人配置上下文的依赖项"""
    # 优先使用 set_client_tenant_context 已经查出来的 site 对象，避免二次查询
    site = getattr(request.state, "site", None)
    if not site:
        site = await crud_site.get(db, id=site_id)

    if not site or not site.bot_config:
        raise HTTPException(status_code=404, detail="未找到对应的站点或配置")

    config = site.bot_config.get("wecom_smart", {})
    if not config or not config.get("enabled"):
        raise HTTPException(status_code=403, detail="该站点未启用企业微信智能机器人")

    token = config.get("token")
    aes_key = config.get("encoding_aes_key")
    if not token or not aes_key:
        raise HTTPException(status_code=500, detail="企业微信机器人配置不完整")

    # 智能机器人的 receiveid 是空串
    crypt = WXBizJsonMsgCrypt(token, aes_key, "")
    return {"site": site, "config": config, "crypt": crypt}


@router.get("/wecom-smart-robot")
async def verify_url(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
    context: dict = Depends(get_wecom_smart_bot_context),
):
    """验证回调 URL (企业微信智能机器人设置时触发)"""
    try:
        decrypted_echostr = WeComSmartService.verify_url(
            context["crypt"], msg_signature, timestamp, nonce, echostr
        )
        return Response(content=decrypted_echostr, media_type="text/plain")
    except ValueError:
        return Response(content="验证失败", media_type="text/plain", status_code=400)


@router.post("/wecom-smart-robot")
async def handle_wecom_message(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    context: dict = Depends(get_wecom_smart_bot_context),
):
    """处理企业微信智能机器人消息回调 (JSON 协议)"""
    try:
        post_data = await request.body()
        response_text = await WeComSmartService.process_webhook(
            site=context["site"],
            crypt=context["crypt"],
            post_data=post_data,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
            aes_key=context["config"].get("encoding_aes_key"),
            background_tasks=background_tasks,
        )
        # 即使 reply_payload 没有内容，Service 也会保底返回加密的原文或者 "success"
        if response_text:
            return Response(content=response_text, media_type="text/plain")
        return Response(content="success", media_type="text/plain")
    except Exception as e:
        from starlette.requests import ClientDisconnect

        if isinstance(e, ClientDisconnect):
            logger.warning(
                f"📩 [WeCom] Client disconnected during request body read: site_id={context['site'].id}"
            )
            # 客户端断开通常是由于处理时间过长，直接静默返回
            return Response(content="success", media_type="text/plain")

        logger.exception(f"❌ [WeCom] Unexpected error processing webhook: {e}")
        return Response(status_code=400)


async def get_wecom_kefu_context(site_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    """获取企业微信客服配置上下文的依赖项"""
    site = await crud_site.get(db, id=site_id)
    if not site or not site.bot_config:
        raise HTTPException(status_code=404, detail="未找到对应的站点或配置")

    config = site.bot_config.get("wecom_kefu", {})
    if not config or not config.get("enabled"):
        raise HTTPException(status_code=403, detail="该站点未启用企业微信客服")

    corp_id = config.get("corp_id")
    token = config.get("token")
    aes_key = config.get("encoding_aes_key")
    if not corp_id or not token or not aes_key:
        raise HTTPException(status_code=500, detail="企业微信客服配置不完整")

    # 客服机器人的 receiveid 是企业 CorpID
    crypt = WXBizXmlMsgCrypt(token, aes_key, corp_id)
    return {"site": site, "config": config, "crypt": crypt}


@router.get("/wecom-kefu")
async def verify_kefu_url(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
    context: dict = Depends(get_wecom_kefu_context),
):
    """验证回调 URL (企业微信客服设置时触发)"""
    try:
        decrypted_echostr = WeComKefuService.verify_url(
            context["crypt"], msg_signature, timestamp, nonce, echostr
        )
        return Response(content=decrypted_echostr, media_type="text/plain")
    except ValueError:
        return Response(content="验证失败", media_type="text/plain", status_code=400)


@router.post("/wecom-kefu")
async def handle_kefu_message(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    context: dict = Depends(get_wecom_kefu_context),
):
    """处理企业微信客服消息回调 (XML 协议)"""
    post_data = await request.body()
    try:
        response_text = await WeComKefuService.process_webhook(
            site=context["site"],
            crypt=context["crypt"],
            post_data=post_data,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
            background_tasks=background_tasks,
        )
        return Response(content=response_text, media_type="text/plain")
    except ValueError:
        return Response(status_code=400)


async def get_wecom_app_context(site_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    """获取企业微信应用(机器人)配置上下文的依赖项"""
    site = await crud_site.get(db, id=site_id)
    if not site or not site.bot_config:
        raise HTTPException(status_code=404, detail="未找到对应的站点或配置")

    config = site.bot_config.get("wecom_app", {})
    if not config or not config.get("enabled"):
        raise HTTPException(status_code=403, detail="该站点未启用企业微信机器人")

    corp_id = config.get("corp_id")
    token = config.get("token")
    aes_key = config.get("encoding_aes_key")
    if not corp_id or not token or not aes_key:
        raise HTTPException(status_code=500, detail="企业微信应用配置不完整")

    # 应用机器人的 receiveid 是企业 CorpID
    crypt = WXBizXmlMsgCrypt(token, aes_key, corp_id)
    return {"site": site, "config": config, "crypt": crypt}


@router.get("/wecom-app")
async def verify_app_url(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
    context: dict = Depends(get_wecom_app_context),
):
    """验证回调 URL (企业微信机器人设置时触发)"""
    try:
        decrypted_echostr = WeComAppService.verify_url(
            context["crypt"], msg_signature, timestamp, nonce, echostr
        )
        return Response(content=decrypted_echostr, media_type="text/plain")
    except ValueError:
        return Response(content="验证失败", media_type="text/plain", status_code=400)


@router.post("/wecom-app")
async def handle_app_message(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    context: dict = Depends(get_wecom_app_context),
):
    """处理企业微信机器人消息回调 (XML 协议)"""
    post_data = await request.body()
    try:
        response_text = await WeComAppService.process_webhook(
            site=context["site"],
            crypt=context["crypt"],
            post_data=post_data,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
            background_tasks=background_tasks,
        )
        return Response(content=response_text, media_type="text/plain")
    except Exception as e:
        logger.error(f"处理企业微信应用 Webhook 异常: {e}")
        return Response(status_code=400)
