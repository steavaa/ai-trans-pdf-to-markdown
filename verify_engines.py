"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  三引擎安装完整性验证工具
  Docling · Marker · MinerU

  逐项检查：包导入 → 关键依赖 → 转换器能否正常实例化
  ✅ = 通过   ⚠️ = 需关注   ❌ = 失败
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sys
import importlib
import os
from pathlib import Path

# ============================================================
# 工具函数
# ============================================================

PASS = "✅"
WARN = "⚠️"
FAIL = "❌"
INFO = "ℹ️"


def status_line(label: str, code: str, detail: str = "") -> str:
    """生成一行状态报告"""
    line = f"  {code} {label}"
    if detail:
        line += f"  ({detail})"
    return line


# ============================================================
# A. 环境基础
# ============================================================

def check_environment():
    """检查 Python、PyTorch 等基础环境"""
    print(f"\n{'─' * 50}")
    print(f"  环境基础")
    print(f"{'─' * 50}")

    # Python 版本
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        print(status_line(f"Python {py_ver}", PASS))
    elif sys.version_info >= (3, 8):
        print(status_line(f"Python {py_ver}", WARN, "建议 ≥ 3.10"))
    else:
        print(status_line(f"Python {py_ver}", FAIL, "需 ≥ 3.8"))

    # PyTorch
    try:
        import torch
        cuda_ok = torch.cuda.is_available()
        device_info = f"CUDA: {torch.cuda.get_device_name(0)}" if cuda_ok else "CPU only"
        print(status_line(f"PyTorch {torch.__version__}", PASS, device_info))
    except ImportError:
        print(status_line("PyTorch", FAIL, "未安装，但引擎安装时会自动带上"))
        print("        若缺失，运行：pip install torch")


# ============================================================
# B. Docling
# ============================================================

def check_docling():
    """检查 Docling 安装完整性"""
    print(f"\n{'─' * 50}")
    print(f"  Docling (IBM)")
    print(f"{'─' * 50}")

    # 1. 包导入
    try:
        import docling  # noqa: F401
        print(status_line("包导入", PASS, f"已安装"))
    except ImportError:
        print(status_line("包导入", FAIL, "未安装 → pip install docling"))
        return

    # 2. DocumentConverter 可实例化
    try:
        from docling.document_converter import DocumentConverter
        converter = DocumentConverter()
        print(status_line("转换器实例化", PASS, "模型已就绪"))
    except Exception as e:
        err_msg = str(e)[:80]
        print(status_line("转换器实例化", WARN, f"可能需下载模型：{err_msg}"))

    # 3. 依赖检查
    for pkg in ["transformers", "accelerate"]:
        try:
            importlib.import_module(pkg)
            print(status_line(f"依赖 {pkg}", PASS))
        except ImportError:
            print(status_line(f"依赖 {pkg}", FAIL, f"pip install {pkg}"))


# ============================================================
# C. Marker
# ============================================================

def check_marker():
    """检查 Marker 安装完整性"""
    print(f"\n{'─' * 50}")
    print(f"  Marker（英文论文最优）")
    print(f"{'─' * 50}")

    # 1. 包导入
    try:
        import marker  # noqa: F401
        print(status_line("包导入", PASS, "已安装"))
    except ImportError:
        print(status_line("包导入", FAIL, "未安装 → pip install marker-pdf"))
        return

    # 2. PdfConverter + create_model_dict 可实例化
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        _ = create_model_dict()
        print(status_line("模型字典", PASS, "模型已就绪"))
    except Exception as e:
        err_msg = str(e)[:100]
        if "download" in err_msg.lower() or "not found" in err_msg.lower():
            print(status_line("模型字典", WARN, "模型未下载，首次使用时会自动下载"))
        else:
            print(status_line("模型字典", WARN, err_msg))

    # 3. PdfConverter 可实例化
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        converter = PdfConverter(artifact_dict=create_model_dict())
        print(status_line("转换器实例化", PASS, "就绪"))
    except Exception as e:
        err_msg = str(e)[:100]
        print(status_line("转换器实例化", WARN, f"可能需要下载模型：{err_msg}"))

    # 4. 依赖
    for pkg in ["surya", "torch"]:
        try:
            importlib.import_module(pkg)
            print(status_line(f"依赖 {pkg}", PASS))
        except ImportError:
            print(status_line(f"依赖 {pkg}", FAIL, f"pip install {pkg}"))


# ============================================================
# D. MinerU
# ============================================================

def check_mineru():
    """检查 MinerU 安装完整性"""
    print(f"\n{'─' * 50}")
    print(f"  MinerU（中文论文最优）")
    print(f"{'─' * 50}")

    # 1. 包导入
    try:
        import magic_pdf  # noqa: F401
        print(status_line("包导入", PASS, "已安装"))
    except ImportError:
        print(status_line("包导入", FAIL, "未安装 → pip install magic-pdf"))
        return

    # 2. 核心模块可导入
    try:
        from magic_pdf.pipe.UNIPipe import UNIPipe
        from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter
        print(status_line("核心模块", PASS, "UNIPipe + DiskReaderWriter"))
    except ImportError as e:
        print(status_line("核心模块", FAIL, str(e)[:80]))

    # 3. 依赖检查
    for pkg, desc in [
        ("paddlepaddle", "PaddlePaddle（MinerU 核心依赖）"),
        ("paddleocr", "PaddleOCR"),
    ]:
        try:
            importlib.import_module(pkg)
            print(status_line(f"依赖 {pkg}", PASS))
        except ImportError:
            print(status_line(f"依赖 {pkg}", FAIL, f"需安装 {desc}"))

    # 4. 模型文件检查（常见缓存位置）
    model_dirs = [
        Path.home() / ".magic_pdf",
        Path.home() / ".cache" / "magic_pdf",
        Path.home() / ".cache" / "huggingface" / "hub",
    ]
    found_any = False
    for d in model_dirs:
        if d.exists():
            found_any = True
            break
    if found_any:
        print(status_line("模型缓存", PASS, "检测到缓存目录"))
    else:
        print(status_line("模型缓存", INFO, "首次使用时会自动下载（约 2–3 GB）"))


# ============================================================
# E. 汇总
# ============================================================

def main():
    print("\n" + "=" * 55)
    print("  PDF 转换引擎  安装完整性验证")
    print("  Docling · Marker · MinerU")
    print("=" * 55)

    check_environment()
    check_docling()
    check_marker()
    check_mineru()

    print(f"\n{'─' * 50}")
    print(f"  结果图解")
    print(f"{'─' * 50}")
    print(f"  {PASS} = 通过，可正常使用")
    print(f"  {WARN} = 包已装，模型未下载（首次转 PDF 时自动下载）")
    print(f"  {FAIL} = 未安装或缺少依赖")
    print(f"  {INFO} = 尚无法确认，首次使用时验证")
    print(f"\n  核心原则：只要 {PASS} 包导入通过 + {PASS} 转换器实例化通过")
    print(f"  → 该引擎就完全可用，不缺任何东西。")

    input("\n按 Enter 退出...")


if __name__ == "__main__":
    main()
