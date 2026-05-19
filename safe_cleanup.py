#!/usr/bin/env python3
"""
safe_cleanup.py
===============
安全清理脚本 — 仅处理确认无风险的空目录和缓存文件。

功能:
1. 执行前自动备份到 backup_YYYYMMDD_HHMMSS 文件夹
2. 每处理一个项目前要求确认（或只自动清理低风险项）
3. 清理后验证核心功能文件是否完整

作者: Kimi Code CLI
日期: 2026-05-20
"""

import os
import sys
import shutil
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(PROJECT_ROOT, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

# ---------------------------------------------------------------------------
# 配置：风险分级清理清单
# ---------------------------------------------------------------------------
CLEANUP_ITEMS = {
    "low_risk": [  # 🟢 低风险：空缓存目录，可自动清理
        {"path": "__pycache__", "desc": "根目录空缓存目录 __pycache__/"},
        {"path": "src/__pycache__", "desc": "src 空缓存目录 src/__pycache__/"},
    ],
    "medium_risk": [  # 🟡 中风险：空数据/结果目录，默认保留结构
        {"path": "data/SisFall_dataset/SA01", "desc": "空数据集目录 SA01/（SisFall 占位）"},
        {"path": "data/SisFall_dataset/SA02", "desc": "空数据集目录 SA02/（SisFall 占位）"},
        {"path": "data/SisFall_dataset/SE01", "desc": "空数据集目录 SE01/（SisFall 占位）"},
        {"path": "results/figures", "desc": "空结果目录 results/figures/（论文图表输出）"},
        {"path": "results/thesis", "desc": "空结果目录 results/thesis/（论文结果）"},
    ],
    "high_risk": [  # 🔴 高风险：项目结构依赖，必须保留
        {"path": "templates", "desc": "Flask 模板目录 templates/（web_app.py render_template 依赖）"},
        {"path": "src", "desc": "源码目录 src/（web_app.py import 依赖）"},
        {"path": "data", "desc": "数据根目录 data/"},
        {"path": "results", "desc": "结果根目录 results/"},
        {"path": "venv", "desc": "Python 虚拟环境 venv/（切勿删除）"},
    ]
}

CORE_FILES = [
    "web_app.py",
    "src/__init__.py",
    "src/fall_detection.py",
    "src/secret_sharing.py",
    "client.py",
]


def print_banner():
    print("=" * 60)
    print("  FallDetectionMPC 安全清理脚本")
    print("=" * 60)
    print(f"  项目根目录: {PROJECT_ROOT}")
    print(f"  备份目录:  {BACKUP_DIR}")
    print("=" * 60)
    print()


def backup_project():
    """执行前自动全量备份（排除 venv 和 .git）。"""
    print("[1/4] 正在创建全量备份...")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    exclude = {'.git', 'venv', '__pycache__', 'backup_'}
    items = [item for item in os.listdir(PROJECT_ROOT)
             if not any(item.startswith(ex) for ex in exclude) and item != os.path.basename(BACKUP_DIR)]
    
    for item in items:
        src = os.path.join(PROJECT_ROOT, item)
        dst = os.path.join(BACKUP_DIR, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    
    print(f"      ✅ 备份完成: {BACKUP_DIR}")
    print(f"      📦 已备份 {len(items)} 个条目")
    print()


def is_empty_dir(path: str) -> bool:
    """检查目录是否为空（递归检查：无任何文件）。"""
    full = os.path.join(PROJECT_ROOT, path)
    if not os.path.isdir(full):
        return False
    for root, dirs, files in os.walk(full):
        if files:
            return False
    return True


def prompt_yes_no(question: str, default: str = "n") -> bool:
    """询问用户确认。"""
    hint = "[Y/n]" if default.lower() == "y" else "[y/N]"
    while True:
        ans = input(f"      {question} {hint}: ").strip().lower()
        if not ans:
            ans = default.lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("      请输入 y 或 n")


def cleanup_low_risk():
    """清理低风险项目（空缓存目录）。"""
    print("[2/4] 低风险项清理（空缓存目录）")
    removed = []
    for item in CLEANUP_ITEMS["low_risk"]:
        path = item["path"]
        full = os.path.join(PROJECT_ROOT, path)
        if os.path.exists(full) and is_empty_dir(path):
            print(f"      🟢 {item['desc']}")
            if prompt_yes_no("        是否删除?", default="y"):
                shutil.rmtree(full)
                print(f"        ✅ 已删除: {path}")
                removed.append(path)
            else:
                print(f"        ⏭️ 已跳过: {path}")
        elif os.path.exists(full):
            print(f"      ⚠️  {item['desc']} — 非空，跳过")
        else:
            print(f"      ℹ️  {item['desc']} — 不存在，跳过")
    print()
    return removed


def cleanup_medium_risk():
    """清理中风险项目（空数据/结果目录）— 默认不清理，仅询问。"""
    print("[3/4] 中风险项清理（空数据/结果目录）")
    print("      ⚠️  这些目录虽然为空，但属于项目结构占位。")
    print("         删除后可能需要手动重建。")
    removed = []
    for item in CLEANUP_ITEMS["medium_risk"]:
        path = item["path"]
        full = os.path.join(PROJECT_ROOT, path)
        if os.path.exists(full) and is_empty_dir(path):
            print(f"      🟡 {item['desc']}")
            if prompt_yes_no("        是否删除?", default="n"):
                shutil.rmtree(full)
                print(f"        ✅ 已删除: {path}")
                removed.append(path)
            else:
                print(f"        ⏭️ 已跳过: {path}")
        elif os.path.exists(full):
            print(f"      ⚠️  {item['desc']} — 非空，跳过")
        else:
            print(f"      ℹ️  {item['desc']} — 不存在，跳过")
    print()
    return removed


def verify_core_files():
    """验证核心功能文件是否完整。"""
    print("[4/4] 核心文件完整性验证")
    missing = []
    present = []
    for f in CORE_FILES:
        full = os.path.join(PROJECT_ROOT, f)
        if os.path.exists(full):
            size = os.path.getsize(full)
            print(f"      ✅ {f:<35} ({size:>6} bytes)")
            present.append(f)
        else:
            print(f"      ❌ {f:<35} (缺失)")
            missing.append(f)
    print()
    
    if missing:
        print("⚠️  警告: 以下核心文件缺失，项目可能无法运行:")
        for f in missing:
            print(f"   - {f}")
    else:
        print("✅ 所有核心文件完整")
    
    print(f"\n📊 统计: 存在 {len(present)}/{len(CORE_FILES)} 个核心文件")
    print(f"🗑️  本次清理: 共删除 {len(removed_all)} 个项目")
    print(f"💾 备份位置: {BACKUP_DIR}")
    print("\n" + "=" * 60)
    print("  清理完成。如需恢复，请从 backup_ 目录手动还原。")
    print("=" * 60)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print_banner()
    
    if not prompt_yes_no("是否开始清理流程?", default="n"):
        print("已取消")
        sys.exit(0)
    
    backup_project()
    
    removed_low = cleanup_low_risk()
    removed_med = cleanup_medium_risk()
    removed_all = removed_low + removed_med
    
    verify_core_files()
