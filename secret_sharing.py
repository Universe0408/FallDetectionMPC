"""
secret_sharing.py
=================
秘密分享基础模块。

提供两方加法秘密分享 (2-out-of-2 Additive Secret Sharing) 的核心操作：
- 拆分 (share): x -> (x0, x1)，满足 x0 + x1 ≡ x (mod MOD)
- 重构 (reconstruct): (x0, x1) -> x

所有运算在 Z_{2^32} 环上进行。
"""

import random

MOD = 2 ** 32


def share(x: int) -> tuple:
    """
    将明文整数 x 拆分为两方份额。
    
    返回 (x0, x1)，满足 (x0 + x1) % MOD == x % MOD。
    单方无法推断原始值。
    """
    x = int(x) % MOD
    x0 = random.randint(0, MOD - 1)
    x1 = (x - x0) % MOD
    return (x0, x1)


def reconstruct(x0: int, x1: int) -> int:
    """
    从两方份额重构明文值。
    
    返回 (x0 + x1) % MOD。
    注意：真实 MPC 场景中，重构需要两方联合授权。
    """
    return (int(x0) + int(x1)) % MOD
