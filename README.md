```markdown
# 隐私保护跌倒检测系统 (MPC-FallDetection)

[![Python](https://img.shields.io/badge/Python-3.9-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0-green)](https://flask.palletsprojects.com/)
[![MPC](https://img.shields.io/badge/MPC-Arithmetic%20Secret%20Sharing-orange)](https://en.wikipedia.org/wiki/Secure_multi-party_computation)

基于**安全多方计算（MPC）**的穿戴式跌倒检测系统。在云端实现“数据可用不可见”——原始加速度数据全程加密，仅输出跌倒判定结果。

## 🎯 主要特性

- **两阶段阈值检测**：冲击检测（SVM 幅值）+ 姿态检测（倾斜角）
- **端到端隐私保护**：算术秘密分享 + Beaver 三元组安全乘法
- **Web 可视化演示**：Flask 界面，实时展示 MPC 中间步骤
- **SisFall 数据集基准测试**：一键评估准确率、混淆矩阵
- **两种检测模式**：标准模式（94% 准确率） / 高速模式（单阶段）

## 📊 性能指标（SisFall 测试集）

| 指标 | 明文基线 | MPC 隐私保护 |
|------|----------|---------------|
| 准确率 | 96.0% | **94.0%** |
| 精确率 | 96.0% | **94.0%** |
| 召回率 | 96.0% | **94.0%** |
| F1 分数 | 0.960 | **0.940** |

- 单样本端到端延迟：约 **700 ms**（标准模式）
- 精度损失：仅 **2%**（源于定点数量化误差）
- 安全性：半诚实模型下信息论安全

## 🚀 快速开始

### 1. 克隆仓库
```bash
git clone https://github.com/你的用户名/你的仓库名.git
cd 你的仓库名
```

2. 安装依赖

```bash
pip install flask numpy
```

3. 运行 Web 演示

```bash
python web_app.py
```

浏览器访问 http://127.0.0.1:5000

4. 运行数据集基准测试

```bash
python client.py
```

（需将 SisFall 数据集放入 data/SisFall_dataset/）

📁 项目结构

```
.
├── web_app.py                # Flask Web 入口 + MPC 模拟器
├── client.py                 # SisFall 数据集基准测试
├── safe_cleanup.py           # 项目清理脚本（保留核心文件）
├── src/
│   ├── __init__.py
│   ├── fall_detection.py     # 安全跌倒检测核心（MPC 运算）
│   └── secret_sharing.py     # 算术秘密分享基础模块
├── templates/                # HTML 前端模板（index.html）
├── data/                     # 数据集目录（SisFall 等）
├── results/                  # 结果输出目录
└── detections.db             # SQLite 检测历史（运行后生成）
```

🔐 隐私保护原理

1. 数据采集：客户端将加速度数据定点化为整数（scale=10000）
2. 秘密分享：每个数拆分为两个随机份额 [x] = (x0, x1)，分别发送给两台云服务器
3. 安全计算：
   · 本地加法：份额相加 → 零通信
   · 安全乘法：Beaver 三元组 → 1 轮通信
   · 安全比较：掩码比较 → 多轮通信
4. 结果重构：两方将 [fall] 份额返回客户端，本地相加得到最终判定

🧪 实验复现

· 数据集：SisFall（19–75 岁受试者，200 Hz 采样）
· 阈值参数：冲击阈值 2g，姿态阈值 60°
· 运行基准：python client.py 自动输出精度、混淆矩阵

📄 相关论文

本项目的技术细节来源于作者本科毕业论文
《基于高效安全多方计算的隐私保护跌倒检测系统》
（如需详细内容，请联系作者）

注：为保护个人隐私，论文原文未包含在此仓库中。

📜 许可证

MIT License（可自行修改）

🙏 致谢

· SisFall 数据集提供者：哥伦比亚安蒂奥基亚大学
· 指导教师：杨安家（暨南大学网络空间安全学院）

```
