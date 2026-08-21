import logging
from hashlib import md5

from aes_pkcs5.algorithms.aes_ecb_pkcs5_padding import AESECBPKCS5Padding

logger = logging.getLogger(__name__)


def create_sign(*args) -> str:
    """生成 MD5 签名：拼接参数 + 固定盐值。None 按空字符串处理。"""
    try:
        parts = ["" if a is None else str(a) for a in args]
        sign_str = "".join(parts) + "3478cbbc33f84bd00d75d7dfa69e0daa"
        return md5(sign_str.encode("utf-8")).hexdigest()
    except Exception as e:
        logger.error(f"签名生成失败: {e}")
        raise ValueError(f"签名生成失败: {str(e)}") from e


def aes_encrypt(
    plaintext: str,
    key: str = "23DbtQHR2UMbH6mJ",
    out_format: str = "hex",
) -> str:
    if plaintext is None:
        raise ValueError("加密失败: plaintext 不能为空")
    try:
        cipher = AESECBPKCS5Padding(key, out_format)
        return cipher.encrypt(str(plaintext))
    except Exception as e:
        logger.error(f"加密失败: {e}")
        raise ValueError(f"加密失败: {str(e)}") from e


def aes_decrypt(
    ciphertext: str,
    key: str = "23DbtQHR2UMbH6mJ",
    out_format: str = "hex",
) -> str:
    try:
        cipher = AESECBPKCS5Padding(key, out_format)
        return cipher.decrypt(ciphertext)
    except Exception as e:
        logger.error(f"解密失败: {e}")
        raise ValueError(f"解密失败: {str(e)}") from e
