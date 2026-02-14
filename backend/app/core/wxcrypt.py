
import base64
import hashlib
import logging
import os
import struct
import time
import xml.etree.ElementTree as ET

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

logger = logging.getLogger(__name__)


class PKCS7Encoder:
    """RFC 2315 PKCS#7 padding"""

    block_size = 32

    @classmethod
    def encode(cls, text_bytes):
        amount_to_pad = cls.block_size - (len(text_bytes) % cls.block_size)
        pad = bytes([amount_to_pad] * amount_to_pad)
        return text_bytes + pad

    @classmethod
    def decode(cls, decrypted_bytes):
        pad = decrypted_bytes[-1]
        if pad < 1 or pad > cls.block_size:
            pad = 0
        return decrypted_bytes[:-pad]


class WXBizMsgCrypt:
    def __init__(self, token, encoding_aes_key, receive_id):
        self.token = token
        # Handle potential padding issues for 43-char keys
        aes_key = encoding_aes_key + "="
        try:
            self.key = base64.b64decode(aes_key)
        except binascii.Error:
             # Retry with standard padding if needed
             missing_padding = len(encoding_aes_key) % 4
             if missing_padding:
                 aes_key = encoding_aes_key + "=" * (4 - missing_padding)
             self.key = base64.b64decode(aes_key)
        self.receive_id = receive_id

    def verify_signature(self, msg_signature, timestamp, nonce, echostr):
        sort_list = [self.token, timestamp, nonce, echostr]
        sort_list.sort()
        sha1 = hashlib.sha1()
        sha1.update("".join(sort_list).encode("utf-8"))
        hash_code = sha1.hexdigest()
        return hash_code == msg_signature

    def decrypt(self, text, msg_signature, timestamp, nonce):
        # 1. Verify Signature
        sort_list = [self.token, timestamp, nonce, text]
        sort_list.sort()
        sha1 = hashlib.sha1()
        sha1.update("".join(sort_list).encode("utf-8"))
        if sha1.hexdigest() != msg_signature:
            raise Exception("Signature verification failed")

        # 2. AES Decrypt
        cipher = Cipher(
            algorithms.AES(self.key), modes.CBC(self.key[:16]), backend=default_backend()
        )
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(base64.b64decode(text)) + decryptor.finalize()

        # 3. Handle PKCS7 padding
        decrypted = PKCS7Encoder.decode(decrypted)

        # 4. Extract content
        # Random(16) + MsgLen(4) + Msg + ReceiveID
        msg_len = struct.unpack(">I", decrypted[16:20])[0]
        msg_content = decrypted[20 : 20 + msg_len].decode("utf-8")
        receive_id = decrypted[20 + msg_len :].decode("utf-8")

        # Optional: check receive_id
        return msg_content

    def encrypt(self, reply, nonce):
        # Random(16) + MsgLen(4) + Msg + ReceiveID
        random_bytes = hashlib.sha1(str(time.time()).encode()).digest()[:16]
        reply_bytes = reply.encode("utf-8")
        msg_len_bytes = struct.pack(">I", len(reply_bytes))
        receive_id_bytes = self.receive_id.encode("utf-8")

        full_bytes = random_bytes + msg_len_bytes + reply_bytes + receive_id_bytes
        full_bytes = PKCS7Encoder.encode(full_bytes)

        cipher = Cipher(
            algorithms.AES(self.key), modes.CBC(self.key[:16]), backend=default_backend()
        )
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(full_bytes) + encryptor.finalize()

        base64_encrypted = base64.b64encode(encrypted).decode("utf-8")

        # Generate Signature
        timestamp = str(int(time.time()))
        sort_list = [self.token, timestamp, nonce, base64_encrypted]
        sort_list.sort()
        sha1 = hashlib.sha1()
        sha1.update("".join(sort_list).encode("utf-8"))
        signature = sha1.hexdigest()

        return base64_encrypted, signature, timestamp
    @staticmethod
    def build_reply_xml(to_user: str, from_user: str, content: str) -> str:
        """构造企业微信被动回复的明文 XML"""
        return f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{int(time.time())}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>"""
