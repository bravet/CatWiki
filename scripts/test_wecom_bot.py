
import os
import time
import requests
import hashlib
import base64
import uuid
import sys
import argparse
import xml.etree.ElementTree as ET
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# ANSI Colors
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# --- 微信加解密类 (简化版，用于测试端) ---
class WXBizMsgCryptTest:
    def __init__(self, token, aes_key, receive_id):
        self.token = token
        self.aes_key = base64.b64decode(aes_key + "=")
        self.receive_id = receive_id

    def _get_signature(self, timestamp, nonce, encrypt_text):
        sort_list = sorted([self.token, timestamp, nonce, encrypt_text])
        sha1 = hashlib.sha1()
        sha1.update("".join(sort_list).encode("utf-8"))
        return sha1.hexdigest()

    def encrypt(self, text, nonce):
        text_bytes = text.encode("utf-8")
        # 32位随机字节 + 4字节长度 + 内容 + receive_id
        random_bytes = os.urandom(16)
        content_len = len(text_bytes).to_bytes(4, byteorder='big')
        raw_data = random_bytes + content_len + text_bytes + self.receive_id.encode("utf-8")
        
        # PKCS7 填充
        pad_len = 32 - (len(raw_data) % 32)
        raw_data += bytes([pad_len] * pad_len)
        
        cipher = Cipher(algorithms.AES(self.aes_key), modes.CBC(self.aes_key[:16]), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(raw_data) + encryptor.finalize()
        
        encrypt_text = base64.b64encode(encrypted).decode("utf-8")
        timestamp = str(int(time.time()))
        signature = self._get_signature(timestamp, nonce, encrypt_text)
        return encrypt_text, signature, timestamp

    def decrypt(self, encrypt_text, signature, timestamp, nonce):
        # 仅由于测试简单，暂时跳过签名校验
        encrypted = base64.b64decode(encrypt_text)
        cipher = Cipher(algorithms.AES(self.aes_key), modes.CBC(self.aes_key[:16]), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted) + decryptor.finalize()
        
        # 移除 PKCS7 填充
        pad_len = decrypted[-1]
        decrypted = decrypted[:-pad_len]
        
        # 移除前16字节随机数和4字节长度
        content_len = int.from_bytes(decrypted[16:20], byteorder='big')
        content = decrypted[20:20+content_len].decode("utf-8")
        return content

def send_message(api_url, site_id, token, aes_key, message, user_id="test_user"):
    crypt = WXBizMsgCryptTest(token, aes_key, "ww_corp_id_placeholder")
    nonce = "test_nonce_" + str(uuid.uuid4())[:8]
    
    # 模拟用户提问 XML
    plain_xml = f"""<xml>
    <ToUserName><![CDATA[gh_placeholder]]></ToUserName>
    <FromUserName><![CDATA[{user_id}]]></FromUserName>
    <CreateTime>{int(time.time())}</CreateTime>
    <MsgType><![CDATA[text]]></MsgType>
    <Content><![CDATA[{message}]]></Content>
    <MsgId>{int(time.time() * 1000)}</MsgId>
    <AgentID>1</AgentID>
</xml>"""

    try:
        encrypt_text, signature, timestamp = crypt.encrypt(plain_xml, nonce)
    except Exception as e:
        print(f"{Colors.FAIL}❌ 加密失败: {e}{Colors.ENDC}")
        return

    callback_payload = f"""<xml>
    <ToUserName><![CDATA[gh_placeholder]]></ToUserName>
    <Encrypt><![CDATA[{encrypt_text}]]></Encrypt>
</xml>"""

    endpoint = f"{api_url}/v1/bot/wecom-smart-robot"
    params = {
        "msg_signature": signature,
        "timestamp": timestamp,
        "nonce": nonce,
        "site_id": site_id
    }

    print(f"{Colors.BLUE}You:{Colors.ENDC} {message}")
    
    start_time = time.time()
    try:
        resp = requests.post(endpoint, params=params, data=callback_payload, timeout=60)
        duration = time.time() - start_time
        
        if resp.status_code != 200:
            print(f"{Colors.FAIL}❌ Server Error ({resp.status_code}): {resp.text}{Colors.ENDC}")
            return

        if not resp.text:
            print(f"{Colors.WARNING}⚠️  Empty response (Async processing?){Colors.ENDC}")
            return

        root = ET.fromstring(resp.text)
        resp_encrypt_node = root.find("Encrypt")
        if resp_encrypt_node is None:
             print(f"{Colors.FAIL}❌ Invalid response format: {resp.text}{Colors.ENDC}")
             return

        resp_encrypt = resp_encrypt_node.text
        resp_signature = root.find("MsgSignature").text
        resp_timestamp = root.find("TimeStamp").text
        
        reply_xml = crypt.decrypt(resp_encrypt, resp_signature, resp_timestamp, nonce)
        reply_root = ET.fromstring(reply_xml)
        reply_content_node = reply_root.find("Content")
        reply_text = reply_content_node.text if reply_content_node is not None else "[无内容]"
        
        print(f"{Colors.GREEN}AI ({duration:.2f}s):{Colors.ENDC} {reply_text}\n")

    except requests.exceptions.Timeout:
        print(f"{Colors.FAIL}⏰ Request timed out{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}❌ Error: {e}{Colors.ENDC}")

def main():
    parser = argparse.ArgumentParser(description="CatWiki Enterprise WeCom Smart Robot Test Client")
    parser.add_argument("--url", default=os.getenv("API_URL", "http://localhost:3000"), help="API Base URL")
    parser.add_argument("--site-id", default=os.getenv("SITE_ID", "1"), help="Site ID")
    parser.add_argument("-t", "--token", default=os.getenv("WECOM_TOKEN", "test_token_123"), help="WeCom Callback Token")
    parser.add_argument("-k", "--key", default=os.getenv("WECOM_AES_KEY", "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"), help="WeCom EncodingAESKey")
    parser.add_argument("-m", "--message", default="高血压的危害", help="Single message mode (exit after sending)")
    parser.add_argument("-u", "--user", default="test_user_001", help="Simulated User ID")
    
    args = parser.parse_args()

    # Check dependencies
    try:
        import cryptography
    except ImportError:
        print(f"{Colors.FAIL}❌ Missing dependency: cryptography{Colors.ENDC}")
        print("Run: pip install cryptography")
        sys.exit(1)

    print(f"{Colors.HEADER}================================================={Colors.ENDC}")
    print(f"{Colors.HEADER}🤖 CatWiki WeCom Smart Robot Interactive Test{Colors.ENDC}")
    print(f"{Colors.HEADER}================================================={Colors.ENDC}")
    print(f"Target:  {args.url}")
    print(f"Site ID: {args.site_id}")
    print(f"Token:   {args.token}")
    print(f"Key:     {args.key[:6]}...{args.key[-4:]}")
    print("-------------------------------------------------")

    if args.message:
        send_message(args.url, args.site_id, args.token, args.key, args.message, args.user)
    else:
        print(f"{Colors.WARNING}Tips: Type 'quit', 'exit' or Ctrl+C to stop.{Colors.ENDC}\n")
        try:
            while True:
                user_input = input(f"{Colors.BLUE}You > {Colors.ENDC}").strip()
                if not user_input:
                    continue
                if user_input.lower() in ['quit', 'exit']:
                    break
                send_message(args.url, args.site_id, args.token, args.key, user_input, args.user)
        except KeyboardInterrupt:
            print("\nBye!")

if __name__ == "__main__":
    main()
