"""
fall_detection.py
=================
安全跌倒检测核心模块。

提供基于两方安全计算 (2PC) 的隐私保护跌倒检测：
- SecureFallDetection: 主检测器，含数据预处理和秘密分享
- MPCOperations: MPC 基础运算（安全加/乘/比较/AND）
- BeaverTripleGen: Beaver 乘法三元组生成器

所有运算在 Z_{2^32} 整数环上进行，采用定点数表示（scale=10000）。
"""

import random
from src.secret_sharing import share, reconstruct, MOD

# 定点化缩放因子: 1g = 10000
SCALE = 10000

# 冲击阈值: 1.25g 的定点平方值 (≈ 12.25 m/s²)
THRESH_IMPACT_SQ = int((1.25 * SCALE) ** 2) % MOD


class BeaverTripleGen:
    """
    Beaver 乘法三元组生成器（离线阶段 Dealer）。

    为安全乘法预生成随机三元组 (α, β, γ)，满足 γ = α · β。
    三方份额格式: t0=(α0,β0,γ0), t1=(α1,β1,γ1)。
    """

    def generate(self) -> tuple:
        """生成一组 Beaver 三元组的两方份额。"""
        alpha = random.randint(0, MOD - 1)
        beta = random.randint(0, MOD - 1)
        gamma = (alpha * beta) % MOD
        a0, a1 = share(alpha)
        b0, b1 = share(beta)
        c0, c1 = share(gamma)
        return (a0, b0, c0), (a1, b1, c1)


class MPCOperations:
    """
    MPC 基础运算集合。

    封装两方安全计算所需的基础操作：
    - secure_add:      本地安全加法（零通信）
    - secure_mul_scalar: 安全乘常数（零通信）
    - secure_multiply: Beaver 三元组安全乘法（1轮通信）
    - secure_compare:  安全比较 x > y（简化实现，1轮通信）
    - secure_and:      安全逻辑与（基于安全乘法）
    """

    def __init__(self):
        self.triple_gen = BeaverTripleGen()

    @staticmethod
    def secure_add(share_a: tuple, share_b: tuple) -> tuple:
        """
        本地安全加法。
        [z] = [a] + [b]，各方本地相加自己的份额即可。
        """
        return ((share_a[0] + share_b[0]) % MOD,
                (share_a[1] + share_b[1]) % MOD)

    @staticmethod
    def secure_mul_scalar(share_x: tuple, k: int) -> tuple:
        """
        安全乘常数 k。
        [z] = k · [x]，各方本地将份额乘以 k。
        """
        return ((share_x[0] * k) % MOD,
                (share_x[1] * k) % MOD)

    def secure_multiply(self, a0: int, a1: int, b0: int, b1: int,
                        t0: tuple, t1: tuple) -> tuple:
        """
        Beaver 三元组安全乘法。

        输入:
            a0,a1: 被乘数 [a] 的两方份额
            b0,b1: 乘数 [b] 的两方份额
            t0,t1: Beaver 三元组 (α,β,γ) 的两方份额

        协议（1轮通信重构 e,f）:
            e = a - α,  f = b - β  （本地计算后交换重构 e,f）
            z0 = e·f + e·β0 + f·α0 + γ0
            z1 =        e·β1 + f·α1 + γ1
        结果: [z] = (z0, z1) 满足 z = a · b。
        """
        alpha0, beta0, gamma0 = t0
        alpha1, beta1, gamma1 = t1

        # 本地计算 e 和 f 的份额
        e0 = (a0 - alpha0) % MOD
        e1 = (a1 - alpha1) % MOD
        f0 = (b0 - beta0) % MOD
        f1 = (b1 - beta1) % MOD

        # 重构 e 和 f（模拟1轮通信）
        e = (e0 + e1) % MOD
        f = (f0 + f1) % MOD

        # 本地计算结果份额
        z0 = (e * f + e * beta0 + f * alpha0 + gamma0) % MOD
        z1 = (e * beta1 + f * alpha1 + gamma1) % MOD
        return (z0, z1)

    def secure_compare(self, x0: int, x1: int, threshold) -> tuple:
        """
        安全比较: x > threshold ?

        参数:
            x0,x1: 被比较数 [x] 的两方份额
            threshold: 明文整数或份额元组 (t0,t1)

        返回:
            [bit] = (bit0, bit1)，bit ∈ {0,1}。

        ⚠️ 当前为教学/演示级简化实现：
            在内部重构明文进行比较后再分享结果。
            真实生产环境应使用比特分解安全比较协议。
        """
        x = (x0 + x1) % MOD
        if isinstance(threshold, tuple):
            t = (threshold[0] + threshold[1]) % MOD
        else:
            t = int(threshold) % MOD
        result = 1 if x > t else 0
        return share(result)

    def secure_and(self, bit_a: tuple, bit_b: tuple) -> tuple:
        """
        安全逻辑与: result = a AND b

        利用 a ∧ b = a · b（当 a,b ∈ {0,1} 时），
        调用安全乘法实现。
        """
        t0, t1 = self.triple_gen.generate()
        return self.secure_multiply(
            bit_a[0], bit_a[1],
            bit_b[0], bit_b[1],
            t0, t1
        )


class SecureFallDetection:
    """
    隐私保护跌倒检测器。

    职责:
    1. 将浮点加速度数据定点化为 Z_{2^32} 上的整数
    2. 对定点化数据执行两方秘密分享
    3. 提供 MPC 运算接口供上层模拟器调用
    """

    def __init__(self):
        self.ops = MPCOperations()
        self.SCALE = SCALE
        self.MOD = MOD
        self.THRESH_IMPACT_SQ = THRESH_IMPACT_SQ

    def preprocess_data(self, ax_g: float, ay_g: float, az_g: float) -> tuple:
        """
        数据预处理：将 g 单位浮点数定点化。

        返回:
            (ax_f, ay_f, az_f): 定点整数，scale=10000
        """
        ax_f = int(round(ax_g * self.SCALE))
        ay_f = int(round(ay_g * self.SCALE))
        az_f = int(round(az_g * self.SCALE))
        return ax_f, ay_f, az_f

    def share_sensor_data(self, ax_f: int, ay_f: int, az_f: int) -> tuple:
        """
        对三轴定点化数据执行秘密分享。

        返回:
            ((ax0, ax1), (ay0, ay1), (az0, az1))
        """
        return share(ax_f), share(ay_f), share(az_f)
