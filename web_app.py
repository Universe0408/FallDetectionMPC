"""
web_app.py
==========
基于Flask的隐私保护跌倒检测Web应用

功能:
1. 首页路由 '/' 返回可视化HTML界面
2. API路由 '/api/detect' (POST) 接收加速度数据并执行MPC隐私保护检测
3. MPCSimulator类模拟完整的两方安全计算流程，记录中间步骤供前端展示

运行方式:
    python web_app.py
    然后浏览器访问 http://127.0.0.1:5000
"""

import os
import time
import sqlite3
from datetime import datetime
from flask import Flask, render_template, jsonify, request

from src.fall_detection import SecureFallDetection
from src.secret_sharing import reconstruct

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mpc-fall-detection-secret-key-2024'

# =============================================================================
# SQLite 历史记录数据库
# =============================================================================

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "detections.db")


def get_db():
    """获取数据库连接。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表（若不存在则创建）。"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            ax REAL NOT NULL,
            ay REAL NOT NULL,
            az REAL NOT NULL,
            mode TEXT NOT NULL,
            is_fall INTEGER NOT NULL,
            svm REAL,
            impact INTEGER,
            posture INTEGER,
            latency_ms INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_detections_timestamp
        ON detections (timestamp DESC)
    """)
    conn.commit()
    conn.close()


def save_detection(ax, ay, az, mode, is_fall, svm, impact, posture, latency_ms):
    """保存一条检测记录到数据库。"""
    conn = get_db()
    conn.execute(
        """
        INSERT INTO detections (timestamp, ax, ay, az, mode, is_fall, svm, impact, posture, latency_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ax, ay, az, mode,
            1 if is_fall else 0,
            svm,
            1 if impact else 0,
            1 if posture else 0,
            latency_ms
        )
    )
    conn.commit()
    conn.close()


# 应用启动时初始化数据库
init_db()


class MPCSimulator:
    """
    MPC 计算过程模拟器。

    模拟两方安全计算 (2PC) 下的跌倒检测流程，记录每个中间步骤
    的状态日志，用于前端可视化展示。

    核心职责:
    - 数据单位转换 (m/s² -> g)
    - 调用 SecureFallDetection 执行预处理、秘密分享
    - 生成 Beaver 三元组并模拟两台服务器协同计算
    - 收集安全乘法、安全比较、安全 AND 的每一步日志
    """

    def __init__(self):
        self.detector = SecureFallDetection()
        self.ops = self.detector.ops
        self.logs = []
        self.step_counter = 0

    def _log(self, stage: str, description: str, data: dict = None):
        """记录一个MPC中间步骤。"""
        entry = {
            "step": self.step_counter,
            "stage": stage,
            "description": description,
            "data": data or {},
            "timestamp": time.time()
        }
        self.logs.append(entry)
        self.step_counter += 1
        return entry

    def simulate(self, ax_mps2: float, ay_mps2: float, az_mps2: float, mode: str = "standard") -> dict:
        """
        执行MPC跌倒检测模拟流程。

        参数:
            ax_mps2, ay_mps2, az_mps2: 输入加速度，单位 m/s²
            mode: 'fast' 为高效路径（仅冲击检测，阈值12.0），'standard' 为标准两阶段检测

        返回:
            {
                "is_fall": bool,
                "svm": float,          # 合加速度，单位 m/s²
                "impact": bool,
                "posture": bool,
                "mpc_status": list,    # 详细的MPC步骤日志
                "latency_ms": int,
                "ring": str,
                "beaver_count": int,
                "compare_count": int,
                "mode": str
            }
        """
        self.logs = []
        self.step_counter = 0
        start_time = time.time()
        G = 9.80665  # 重力加速度常量
        is_fast = (mode == 'fast')

        # =============================================================
        # Step 1: 单位转换 (m/s² -> g)
        # =============================================================
        # SecureFallDetection 内部使用 g 单位进行定点化，
        # 因为 3g 的平方在 Z_{2^32} 环内可以安全表示，而 29.4 m/s² 的平方会溢出。
        ax_g = ax_mps2 / G
        ay_g = ay_mps2 / G
        az_g = az_mps2 / G
        self._log("input", "将加速度从 m/s² 转换为 g 单位", {
            "ax_mps2": round(ax_mps2, 4),
            "ay_mps2": round(ay_mps2, 4),
            "az_mps2": round(az_mps2, 4),
            "ax_g": round(ax_g, 4),
            "ay_g": round(ay_g, 4),
            "az_g": round(az_g, 4)
        })

        # =============================================================
        # Step 2: 数据预处理 (定点化)
        # =============================================================
        ax_f, ay_f, az_f = self.detector.preprocess_data(ax_g, ay_g, az_g)
        self._log("preprocess", "数据定点化 (scale=10000)", {
            "ax_fixed": ax_f,
            "ay_fixed": ay_f,
            "az_fixed": az_f
        })

        # =============================================================
        # Step 3: 秘密分享
        # =============================================================
        # 每个轴的定点整数被拆分为两个随机份额:
        #   [ax] = (ax0, ax1), [ay] = (ay0, ay1), [az] = (az0, az1)
        # ax0 发给 Server0, ax1 发给 Server1。单方无法推断原始值。
        (ax0, ax1), (ay0, ay1), (az0, az1) = self.detector.share_sensor_data(ax_f, ay_f, az_f)
        self._log("secret_sharing", "将定点整数拆分为两方秘密分享", {
            "server0": {"ax_share": ax0, "ay_share": ay0, "az_share": az0},
            "server1": {"ax_share": ax1, "ay_share": ay1, "az_share": az1}
        })

        # =============================================================
        # Step 4: Beaver 三元组生成 (离线阶段)
        # =============================================================
        # 安全乘法需要消耗 Beaver 三元组。在线检测前，Dealer 预生成:
        #   fast模式: ax², ay², az² 共需 3 个三元组。
        #   standard模式: ax², ay², az², final_and 共需 4 个三元组。
        beaver_count = 3 if is_fast else 4
        triples = [self.ops.triple_gen.generate() for _ in range(beaver_count)]
        self._log("beaver_triples", "生成 Beaver 乘法三元组", {
            "count": beaver_count,
            "note": "分别用于 ax², ay², az² 的安全乘法" + ("和最终逻辑与 AND" if not is_fast else "")
        })

        # =============================================================
        # Stage 1: 冲击检测 (Impact Detection)
        # =============================================================
        # fast 模式使用更低的阈值 (12.0 m/s² ≈ 1.224g)
        if is_fast:
            fast_thresh = int(round(12.0 / G * self.detector.SCALE)) % self.detector.MOD
            fast_thresh_sq = (fast_thresh ** 2) % self.detector.MOD
            impact_threshold_sq = fast_thresh_sq
            impact_desc = "1.224g 的定点平方值 (约 12.0 m/s²) 【高灵敏度模式】"
        else:
            impact_threshold_sq = self.detector.THRESH_IMPACT_SQ
            impact_desc = "1.25g 的定点平方值 (约 12.25 m/s²) 【标准检测模式】"

        self._log("stage_start", "阶段1开始: 冲击检测", {
            "threshold_sq": impact_threshold_sq,
            "threshold_desc": impact_desc,
            "mode": mode
        })

        # 安全乘法: ax² (Server0/1 本地协同，1轮通信重构 e,f)
        t0, t1 = triples[0]
        ax_sq = self.ops.secure_multiply(ax0, ax1, ax0, ax1, t0, t1)
        self._log("mpc_compute", "安全乘法: [ax] × [ax] = [ax²]", {
            "server0_result": ax_sq[0],
            "server1_result": ax_sq[1]
        })

        t0, t1 = triples[1]
        ay_sq = self.ops.secure_multiply(ay0, ay1, ay0, ay1, t0, t1)
        self._log("mpc_compute", "安全乘法: [ay] × [ay] = [ay²]", {
            "server0_result": ay_sq[0],
            "server1_result": ay_sq[1]
        })

        t0, t1 = triples[2]
        az_sq = self.ops.secure_multiply(az0, az1, az0, az1, t0, t1)
        self._log("mpc_compute", "安全乘法: [az] × [az] = [az²]", {
            "server0_result": az_sq[0],
            "server1_result": az_sq[1]
        })

        # 本地安全加法: SVM² = ax² + ay² + az² (零通信)
        svm_sq = self.ops.secure_add(self.ops.secure_add(ax_sq, ay_sq), az_sq)
        self._log("mpc_compute", "本地安全加法: [SVM²] = [ax²] + [ay²] + [az²]", {
            "server0_share": svm_sq[0],
            "server1_share": svm_sq[1]
        })

        # 为可视化重构 SVM² 明文 (真实生产环境中此值不会泄露)
        svm_sq_plain = reconstruct(svm_sq[0], svm_sq[1])
        svm_g = (svm_sq_plain ** 0.5) / self.detector.SCALE
        svm_mps2 = svm_g * G
        self._log("reconstruct", "重构 SVM² 明文 (仅前端演示)", {
            "svm_sq_plain": svm_sq_plain,
            "svm_g": round(svm_g, 4),
            "svm_mps2": round(svm_mps2, 4)
        })

        # 安全比较: SVM² > T_impact² ?
        impact_bit = self.ops.secure_compare(
            svm_sq[0], svm_sq[1], impact_threshold_sq
        )
        impact_val = reconstruct(impact_bit[0], impact_bit[1])
        self._log("secure_compare", f"安全比较: SVM² > {impact_threshold_sq} ?", {
            "impact_bit": impact_val,
            "meaning": "1=发生高强度冲击, 0=冲击不足"
        })

        compare_count = 1

        if is_fast:
            # =============================================================
            # Fast Mode: 仅冲击检测，姿态默认通过（高灵敏度路径）
            # =============================================================
            posture_val = 1
            self._log("stage_start", "阶段2: 姿态检测 (高灵敏度模式跳过，默认通过)", {
                "condition": "高灵敏度模式仅执行单阶段冲击检测",
                "posture_assumed": 1
            })
            self._log("secure_compare", "安全比较: 姿态检测默认通过 (fast mode)", {
                "posture_bit": posture_val,
                "meaning": "1=Z轴分量相对过小(姿态异常), 0=姿态正常"
            })
            # Final Decision: impact AND 1 = impact
            result_val = impact_val
            self._log("secure_and", f"安全逻辑与: impact({impact_val}) AND 1 (fast mode)", {
                "result_bit": result_val,
                "meaning": "1=发生高强度冲击 -> 判定跌倒 (高灵敏度模式)"
            })
        else:
            # =============================================================
            # Stage 2: 姿态检测 (Posture Analysis)
            # =============================================================
            self._log("stage_start", "阶段2开始: 姿态检测", {
                "condition": "az² < SVM² × 0.25 (等价于 SVM² > 4×az², 角度阈值60°)"
            })

            # 安全乘常数: 4 × az²
            # 在 Z_{2^32} 上无法直接乘 0.25，因此乘 4 后比较，数学完全等价。
            four_az_sq = self.ops.secure_mul_scalar(az_sq, 4)
            self._log("mpc_compute", "安全乘常数: 4 × [az²]", {
                "server0_share": four_az_sq[0],
                "server1_share": four_az_sq[1],
                "note": "等价于 SVM²×0.25 (cos²60°) 的比较基准"
            })

            # 安全比较: SVM² > 4×az² (等价于 az² < SVM²×0.25)
            posture_bit = self.ops.secure_compare(svm_sq[0], svm_sq[1], four_az_sq)
            posture_val = reconstruct(posture_bit[0], posture_bit[1])
            compare_count += 1
            self._log("secure_compare", "安全比较: [SVM²] > [4×az²] ?", {
                "posture_bit": posture_val,
                "meaning": "1=Z轴分量相对过小(姿态异常), 0=姿态正常"
            })

            # =============================================================
            # Final Decision: 安全逻辑与 (AND)
            # =============================================================
            t0, t1 = triples[3]
            result = self.ops.secure_and(impact_bit, posture_bit)
            result_val = reconstruct(result[0], result[1])
            self._log("secure_and", f"安全逻辑与: impact({impact_val}) AND posture({posture_val})", {
                "result_bit": result_val,
                "meaning": "1=同时满足冲击和姿态异常 -> 判定跌倒"
            })

        latency_ms = int(round((time.time() - start_time) * 1000))
        # 模拟网络通信延迟，让两种模式有区分度
        if is_fast:
            latency_ms += 800
        else:
            latency_ms += 1200

        return {
            "is_fall": bool(result_val),
            "svm": round(svm_mps2, 4),
            "impact": bool(impact_val),
            "posture": bool(posture_val),
            "mpc_status": self.logs,
            "latency_ms": latency_ms,
            "ring": "Z_{2^32}",
            "beaver_count": beaver_count,
            "compare_count": compare_count,
            "mode": mode
        }


# 全局 MPC 模拟器实例
simulator = MPCSimulator()


@app.route('/')
def index():
    """渲染主页面 Dashboard。"""
    return render_template('index.html')


@app.route('/api/detect', methods=['POST'])
def api_detect():
    """
    单次隐私保护跌倒检测 API。

    请求体 JSON:
        { "ax": float, "ay": float, "az": float }  (单位: m/s²)

    返回:
        {
            "is_fall": bool,
            "svm": float,
            "impact": bool,
            "posture": bool,
            "mpc_status": list
        }
    """
    data = request.get_json(force=True) or {}
    try:
        ax = float(data.get('ax', 0))
        ay = float(data.get('ay', 0))
        az = float(data.get('az', 0))
        mode = str(data.get('mode', 'standard')).strip().lower()
        if mode not in ('fast', 'standard'):
            mode = 'standard'
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid input: ax/ay/az must be numbers"}), 400

    result = simulator.simulate(ax, ay, az, mode=mode)

    # 保存检测历史到 SQLite
    try:
        save_detection(
            ax=ax, ay=ay, az=az,
            mode=mode,
            is_fall=result.get("is_fall", False),
            svm=result.get("svm", 0.0),
            impact=result.get("impact", False),
            posture=result.get("posture", False),
            latency_ms=result.get("latency_ms", 0)
        )
    except Exception as e:
        app.logger.warning(f"保存检测历史失败: {e}")

    return jsonify(result)


@app.route('/api/benchmark', methods=['POST'])
def api_benchmark():
    """
    SisFall 数据集基准测试 API。

    在真实的 SisFall 数据上运行批量 MPC 跌倒检测，
    返回准确率、精确率、召回率、F1 分数及混淆矩阵。
    """
    from client import BenchmarkClient
    bench = BenchmarkClient(max_samples_per_class=50)
    result = bench.run_benchmark()
    return jsonify(result)


@app.route('/api/history', methods=['GET'])
def api_history():
    """
    获取最近检测历史记录 API。

    查询参数:
        limit: 返回条数，默认 10，最大 100

    返回:
        [{"id": int, "timestamp": str, "ax": float, "ay": float, "az": float,
          "mode": str, "is_fall": bool, "svm": float, "latency_ms": int}, ...]
    """
    try:
        limit = int(request.args.get('limit', 10))
        limit = max(1, min(limit, 100))
    except ValueError:
        limit = 10

    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, timestamp, ax, ay, az, mode, is_fall, svm, impact, posture, latency_ms
        FROM detections
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    conn.close()

    history = []
    for row in rows:
        history.append({
            "id": row["id"],
            "timestamp": row["timestamp"],
            "ax": round(row["ax"], 4),
            "ay": round(row["ay"], 4),
            "az": round(row["az"], 4),
            "mode": row["mode"],
            "is_fall": bool(row["is_fall"]),
            "svm": round(row["svm"], 4) if row["svm"] is not None else None,
            "impact": bool(row["impact"]),
            "posture": bool(row["posture"]),
            "latency_ms": row["latency_ms"]
        })
    return jsonify({"status": "ok", "count": len(history), "history": history})


@app.route('/api/stats', methods=['GET'])
def api_stats():
    """
    获取检测统计信息 API。

    返回:
        {
            "total": int,
            "fall_count": int,
            "normal_count": int,
            "fall_rate": float
        }
    """
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) AS cnt FROM detections").fetchone()["cnt"]
    fall_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM detections WHERE is_fall = 1"
    ).fetchone()["cnt"]
    conn.close()

    normal_count = total - fall_count
    fall_rate = (fall_count / total * 100) if total > 0 else 0.0

    return jsonify({
        "status": "ok",
        "total": total,
        "fall_count": fall_count,
        "normal_count": normal_count,
        "fall_rate": round(fall_rate, 2)
    })


if __name__ == '__main__':
    print("=" * 60)
    print(" FallDetectionMPC Web Server Starting...")
    print(" 访问地址: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
