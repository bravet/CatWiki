#!/usr/bin/env python
# Copyright 2026 CatWiki Authors

import json
import logging
import time
import base64

from ..wecom_common import ierror
from ..wecom_common.crypt_base import SHA1, Prpcrypt, throw_exception, FormatException

logger = logging.getLogger(__name__)


class JsonParse:
    """提供提取消息格式中的密文及生成回复消息格式的接口 (JSON 协议)"""

    AES_TEXT_RESPONSE_TEMPLATE = """{
        "encrypt": "%(msg_encrypt)s",
        "msgsignature": "%(msg_signaturet)s",
        "timestamp": "%(timestamp)s",
        "nonce": "%(nonce)s"
    }"""

    def extract(self, jsontext):
        try:
            json_dict = json.loads(jsontext)
            return ierror.WXBizMsgCrypt_OK, json_dict["encrypt"]
        except Exception as e:
            logger.error(f"JSON 解析提取失败: {e}")
            return ierror.WXBizMsgCrypt_ParseJson_Error, None

    def generate(self, encrypt, signature, timestamp, nonce):
        resp_dict = {
            "msg_encrypt": encrypt,
            "msg_signaturet": signature,
            "timestamp": timestamp,
            "nonce": nonce,
        }
        resp_json = self.AES_TEXT_RESPONSE_TEMPLATE % resp_dict
        return resp_json


class WXBizJsonMsgCrypt:
    """企业微信 JSON 消息加解密封装"""

    def __init__(self, sToken, sEncodingAESKey, sReceiveId):
        try:
            missing_padding = len(sEncodingAESKey) % 4
            if missing_padding:
                sEncodingAESKey += "=" * (4 - missing_padding)
            self.key = base64.b64decode(sEncodingAESKey)
            assert len(self.key) == 32
        except Exception:
            throw_exception("[错误]: EncodingAESKey 无效!", FormatException)
        self.m_sToken = sToken
        self.m_sReceiveId = sReceiveId

    def VerifyURL(self, sMsgSignature, sTimeStamp, sNonce, sEchoStr):
        sha1 = SHA1()
        ret, signature = sha1.getSHA1(self.m_sToken, sTimeStamp, sNonce, sEchoStr)
        if ret != 0:
            return ret, None
        if not signature == sMsgSignature:
            return ierror.WXBizMsgCrypt_ValidateSignature_Error, None
        pc = Prpcrypt(self.key)
        ret, sReplyEchoStr = pc.decrypt(sEchoStr, self.m_sReceiveId)
        return ret, sReplyEchoStr

    def EncryptMsg(self, sReplyMsg, sNonce, timestamp=None):
        pc = Prpcrypt(self.key)
        ret, encrypt = pc.encrypt(sReplyMsg, self.m_sReceiveId)
        if ret != 0:
            return ret, None
        encrypt = encrypt.decode("utf-8")
        if timestamp is None:
            timestamp = str(int(time.time()))
        sha1 = SHA1()
        ret, signature = sha1.getSHA1(self.m_sToken, timestamp, sNonce, encrypt)
        if ret != 0:
            return ret, None
        jsonParse = JsonParse()
        return ret, jsonParse.generate(encrypt, signature, timestamp, sNonce)

    def DecryptMsg(self, sPostData, sMsgSignature, sTimeStamp, sNonce):
        jsonParse = JsonParse()
        ret, encrypt = jsonParse.extract(sPostData)
        if ret != 0:
            return ret, None
        sha1 = SHA1()
        ret, signature = sha1.getSHA1(self.m_sToken, sTimeStamp, sNonce, encrypt)
        if ret != 0:
            return ret, None
        if not signature == sMsgSignature:
            logger.error(f"签名不匹配: 计算值={signature}, 预期值={sMsgSignature}")
            return ierror.WXBizMsgCrypt_ValidateSignature_Error, None
        pc = Prpcrypt(self.key)
        ret, json_content = pc.decrypt(encrypt, self.m_sReceiveId)
        return ret, json_content
