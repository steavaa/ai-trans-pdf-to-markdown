# -*- coding: utf-8 -*-
"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  PDF → AI友好 Markdown  三引擎批量转换器
  Windows 11 兼容  |  中文文件名支持  |  2GB 显存安全  |  虚拟环境隔离

  支持的引擎：
    docling → IBM Docling（最稳定，小显存安全）
    marker  → Marker（英文论文最优，公式/表格还原度最高）
    mineru  → MinerU（中文论文断层领先，建议有GPU）
请确保PDF文件名不包含特殊字符（如 #, ?, *, <, > 等），否则可能导致路径解析错误或图片引用失败。
  用法（详见末尾操作清单）：
    1. 把本脚本和所有 PDF 放入 E:\ai\trans to ai
    2. 打开 Windows Terminal → cd 到该目录
    3. 激活虚拟环境 → 运行 python convert_all.py
    4. 选择引擎 → 自动逐篇转换
    5.每个 PDF 会生成一个同名子文件夹，内含：
       - 原始 PDF（备份）
       - 转换后的 .md 文件
       - images/ 图片文件夹--把图片和.MD放入ai即可理解--

  安装（在虚拟环境中按需执行）：
    pip install docling        # Docling（目前只下了这一个，要是用到别的电脑时在配置好python后打开终端powershell,首次需要python -m venv venv 
                                                                                   然后.\venv\Scripts\activate进入虚拟环境，再pip下载,后python verify_engines.py
                                                                                   然后python convert_all.py）
    pip install marker-pdf     # Marker
    pip install magic-pdf      # MinerU(用不了缺库而且需要gpu)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import sys
import subprocess
from pathlib import Path

# ============================================================
# 🔧 自动设置：工作目录 & 缓存位置 & 显存保护
# ============================================================

SOURCE_DIR = Path(__file__).resolve().parent

# 模型缓存放当前目录，不污染 C 盘
if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = str(SOURCE_DIR / ".cache")

# 消除 HF Hub 的 symlink 警告
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


# ============================================================
# 🛡️ 显存检测（用 nvidia-smi，不依赖 torch）
# ============================================================

_AUTO_CPU = False
_VRAM_DETECTED = None

def _get_gpu_memory_mb():
    """通过 nvidia-smi 获取第一块 GPU 总显存（MB）"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip().splitlines()[0].strip())
    except Exception:
        pass
    return None


# 仅在用户未手动干预时自动检测
if os.environ.get("CUDA_VISIBLE_DEVICES", "\0") == "\0":
    _VRAM_DETECTED = _get_gpu_memory_mb()
    if _VRAM_DETECTED is not None and _VRAM_DETECTED <= 2200:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        _AUTO_CPU = True


# ============================================================
# 🧾 其余导入 & 配置
# ============================================================

import shutil
import time
import re

CONFIG = {
    "image_mode": "referenced",
    "skip_existing": True,
    "max_path_length": 240,
}

# ============================================================
# 🔧 Docling 分批处理配置
# ============================================================
BATCH_PAGES = 25   # 每批最多 25 页，8GB 内存绝对安全


# ============================================================
# 🧰 通用工具
# ============================================================

def find_pdfs(source: Path):
    return sorted(
        [f for f in source.glob("*.pdf")
         if f.is_file() and not f.name.startswith("~$")]
    )


def check_path_length(pdf_path: Path):
    test = SOURCE_DIR / pdf_path.stem / "images" / "placeholder.txt"
    length = len(str(test))
    return (False, length) if length > CONFIG["max_path_length"] else (True, length)


def generate_llms_txt(pdf_stem: str, output_dir: Path, pdf_name: str):
    content = (
        f"# {pdf_stem}\n\n"
        f"## What is this paper about?\n"
        f"[在此补充论文主题摘要，或让 AI 分析后回填]\n\n"
        f"## Files in this bundle\n"
        f"- `{pdf_stem}.md` — 论文正文（Markdown 格式）\n"
        f"- `images/` — 论文图片\n"
        f"- `{pdf_name}` — 原始 PDF 备份\n\n"
        f"## Reading notes\n"
        f"- 表格已转为 Markdown / HTML 格式\n"
        f"- 数学公式保留 LaTeX 标记\n"
        f"- 图片引用路径为 `images/xxx.png`\n"
    )
    (output_dir / "llms.txt").write_text(content, encoding="utf-8")


# ============================================================
# 引擎 A：Docling（分页分批，防内存溢出）
# ============================================================

def _export_md(doc, output_dir: Path, md_file: Path):
    """导出 markdown 到指定 .md 文件"""
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    md_content = None
    for args in [
        {"image_export_mode": CONFIG["image_mode"], "image_dir": str(images_dir)},
        {"image_mode": CONFIG["image_mode"], "image_dir": str(images_dir)},
        {"image_mode": CONFIG["image_mode"]},
        {},
    ]:
        try:
            md_content = doc.export_to_markdown(**args)
            break
        except TypeError:
            continue

    if md_content is None:
        raise RuntimeError("导出 Markdown 失败，请升级：pip install --upgrade docling")

    md_file.write_text(md_content, encoding="utf-8")



def _engine_docling(pdf_path: Path, output_dir: Path, md_file: Path):
    from docling.document_converter import DocumentConverter
    import fitz

    src_doc = fitz.open(str(pdf_path))
    total_pages = src_doc.page_count
    src_doc.close()

    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    pdf_stem = pdf_path.stem

    # ── 小 PDF：不分批，直接转 ──
    if total_pages <= BATCH_PAGES:
        converter = DocumentConverter()
        conv_result = converter.convert(str(pdf_path))
        doc = conv_result.document
        _export_md(doc, output_dir, md_file)
        _rename_images_safe(md_file, images_dir, pdf_stem, 1)
        return

    # ── 大 PDF：分批 ──
    print(f"  📐 {total_pages} 页，分批处理（每批 ≤{BATCH_PAGES} 页）")

    total_batches = (total_pages + BATCH_PAGES - 1) // BATCH_PAGES

    for batch_num, start in enumerate(range(0, total_pages, BATCH_PAGES), 1):
        end = min(start + BATCH_PAGES, total_pages) - 1

        # 批次文件名：xxx_p001-025.md
        batch_md_name = f"{pdf_stem}_p{start+1:03d}-{end+1:03d}.md"
        batch_md_file = output_dir / batch_md_name

        # 🔁 断点续跑：如果该批次 .md 已存在，跳过
        if batch_md_file.exists():
            print(f"    ⏭️  [{batch_num}/{total_batches}] 第 {start+1}-{end+1} 页 "
                  f"→ {batch_md_name} 已存在，跳过")
            continue

        batch_pdf = output_dir / f"_tmp_batch_{start}_{end}.pdf"

        # 切出当前批次的子 PDF
        bdoc = fitz.open(str(pdf_path))
        bdoc.select(list(range(start, end + 1)))
        bdoc.save(str(batch_pdf))
        bdoc.close()

        print(f"    🔄 [{batch_num}/{total_batches}] 第 {start+1}-{end+1} 页 "
              f"→ {batch_md_name} ...", end=" ", flush=True)

        try:
            converter = DocumentConverter()
            conv_result = converter.convert(str(batch_pdf))
            doc = conv_result.document
            _export_md(doc, output_dir, batch_md_file)

            # 图片重命名：注入 PDF 来源 + 批次号 + 行号
            _rename_images_safe(batch_md_file, images_dir, pdf_stem, batch_num)

            print("✅")
        finally:
            if batch_pdf.exists():
                batch_pdf.unlink()

    # 生成索引导航
    _write_index(output_dir, pdf_stem, total_batches, total_pages, BATCH_PAGES)

def _rename_images(md_file: Path, images_dir: Path, pdf_stem: str, batch_num: int):
    """
    后处理：把 docling 自动命名的图片重命名为有意义的名字。

    命名格式：
        {pdf_stem}__b{batch_num}__L{行号}__{原名}.png
    """
    if not md_file.exists():
        return

    try:
        raw = md_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as e:
        print(f"\n    ⚠️ 图片重命名：无法读取 {md_file.name}（{e}），跳过")
        return

    lines = raw.split("\n")
    img_ref = re.compile(r'!\[([^\]]*)\]\((images/[^)]+)\)')

    renamed = []
    for i, line in enumerate(lines, 1):
        def _replace(m):
            alt = m.group(1)
            old_rel = m.group(2)
            old_name = Path(old_rel).name
            old_abs = images_dir / old_name

            new_name = f"{pdf_stem}__b{batch_num:02d}__L{i:04d}__{old_name}"
            new_abs = images_dir / new_name

            if old_abs.exists():
                try:
                    old_abs.rename(new_abs)
                except (OSError, FileNotFoundError) as e:
                    print(f"\n    ⚠️ 重命名失败 {old_name}（{e}），保留原名")
                    return f"![{alt}](images/{old_name})"

            return f"![{alt}](images/{new_name})"

        line = img_ref.sub(_replace, line)
        renamed.append(line)

    try:
        md_file.write_text("\n".join(renamed), encoding="utf-8")
    except (OSError, UnicodeError) as e:
        print(f"\n    ⚠️ 图片重命名：无法写回 {md_file.name}（{e}），保留原文")


def _rename_images_safe(md_file: Path, images_dir: Path, pdf_stem: str, batch_num: int):
    """安全包装：重命名失败不中断转换"""
    try:
        _rename_images(md_file, images_dir, pdf_stem, batch_num)
    except Exception as e:
        print(f"\n    ⚠️ 图片重命名异常（{e}），跳过，转换结果不受影响")


def _write_index(output_dir: Path, pdf_stem: str,
                 total_batches: int, total_pages: int, batch_size: int):
    """生成一个 README.md 作为分批文件的导航索引"""
    buf = [
        f"# {pdf_stem}（共 {total_pages} 页，分 {total_batches} 批）\n",
        f"> 由于 PDF 页数较多，已自动分批转换。\n\n",
    ]
    for b in range(1, total_batches + 1):
        s = (b - 1) * batch_size + 1
        e = min(b * batch_size, total_pages)
        fname = f"{pdf_stem}_p{s:03d}-{e:03d}.md"
        buf.append(f"- [{fname}]({fname})  ← 原始 PDF 第 {s}–{e} 页\n")

    buf.append(f"\n💡 使用哪个 .md 就把那个文件 + `images/` 文件夹一起拖入 AI。\n")
    (output_dir / f"{pdf_stem}_README.md").write_text("".join(buf), encoding="utf-8")

# ============================================================
# 引擎 B：Marker
# ============================================================

def _engine_marker(pdf_path: Path, output_dir: Path, md_file: Path):
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict

    converter = PdfConverter(artifact_dict=create_model_dict())
    rendered = converter(str(pdf_path))
    md_content = rendered.markdown

    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(rendered, "images") and rendered.images:
        for img_name, img_bytes in rendered.images.items():
            (images_dir / img_name).write_bytes(img_bytes)

    md_file.write_text(md_content, encoding="utf-8")


# ============================================================
# 引擎 C：MinerU
# ============================================================

def _engine_mineru(pdf_path: Path, output_dir: Path, md_file: Path):
    import tempfile
    from magic_pdf.pipe.UNIPipe import UNIPipe
    from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        rw = DiskReaderWriter(tmpdir)
        pdf_bytes = pdf_path.read_bytes()

        try:
            pipe = UNIPipe(
                pdf_bytes=pdf_bytes, jso_useful_key={}, rw=rw,
                image_dir=str(images_dir),
            )
        except (TypeError, ValueError):
            pipe = UNIPipe(str(pdf_path), rw, image_dir=str(images_dir))

        pipe.pipe_classify()
        pipe.pipe_parse()
        md_content = pipe.pipe_mk_markdown(str(images_dir), drop_mode="none")

    md_file.write_text(md_content, encoding="utf-8")


# ============================================================
# 引擎注册表
# ============================================================

ENGINES = {
    "docling": {
        "name": "Docling (IBM) — 最稳定，小显存安全",
        "func": _engine_docling,
        "install": "pip install docling",
        "recommend": "稳定之选，不易报错，CPU 完全可用",
    },
    "marker": {
        "name": "Marker — 英文论文最优",
        "func": _engine_marker,
        "install": "pip install marker-pdf",
        "recommend": "英文文献首选，公式 / 表格还原度最高",
    },
    "mineru": {
        "name": "MinerU — 中文论文断层领先",
        "func": _engine_mineru,
        "install": "pip install magic-pdf",
        "recommend": "中文文献唯一推荐，强烈建议有 GPU",
    },
}


# ============================================================
# 交互菜单
# ============================================================

def select_engine():
    print("\n" + "─" * 50)
    print("  请选择转换引擎：\n")
    keys = list(ENGINES.keys())
    for i, key in enumerate(keys, 1):
        info = ENGINES[key]
        print(f"  [{i}] {info['name']}")
        print(f"      {info['recommend']}\n")
    print("  [0] 我还没安装，帮我推荐")

    while True:
        try:
            choice = input("\n输入数字 (1-3) 或 0：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消。")
            sys.exit(0)
        if choice == "0":
            return None, None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(keys):
                return keys[idx], ENGINES[keys[idx]]
        except ValueError:
            pass
        print("  请输入 0-3 之间的数字")


def show_recommendation():
    print("\n" + "=" * 50)
    print("  推荐路线")
    print("=" * 50)
    print("""
  你的显卡只有 2GB 显存，强烈建议：

  🥇 英文文献：pip install marker-pdf
              脚本已自动帮你切换到 CPU

  🥈 中文文献：pip install magic-pdf
              脚本已自动帮你切换到 CPU

  🥉 临时用一下：pip install docling（最轻量，CPU 不慢）

  安装完成后重新运行本脚本即可。
""")


# ============================================================
# 主函数
# ============================================================

def main():
    print("\n" + "=" * 58)
    print("  PDF → AI友好 Markdown  三引擎批量转换器")
    print("  " + "─" * 42)
    print("  Docling · Marker · MinerU")
    print("=" * 58)

    # ---- 显示运行设备 ----
    if _AUTO_CPU:
        print(f"\n  ⚠️  检测到显存仅 {_VRAM_DETECTED:.0f} MB（≤ 2GB）")
        print("  🔄 已自动切换为 CPU 模式\n")
    else:
        gpu_disabled = os.environ.get("CUDA_VISIBLE_DEVICES", "") == ""
        if gpu_disabled and _VRAM_DETECTED is None:
            print("\n  🖥️  运行设备：CPU\n")
        elif _VRAM_DETECTED is not None:
            print(f"\n  🖥️  运行设备：GPU（{_VRAM_DETECTED:.0f} MB）\n")

    # ---- 找 PDF ----
    print(f"📂 扫描：{SOURCE_DIR}")
    pdf_files = find_pdfs(SOURCE_DIR)

    if not pdf_files:
        print("  ⚠️  没有找到 PDF 文件。")
        input("\n按 Enter 退出...")
        sys.exit(0)

    skipped_count = sum(
        1 for f in pdf_files
        if CONFIG["skip_existing"]
        and ((SOURCE_DIR / f.stem / f"{f.stem}.md").exists()
         or (SOURCE_DIR / f.stem / f"{f.stem}_README.md").exists())
    )

    print(f"  找到 {len(pdf_files)} 个 PDF"
          f"（其中 {skipped_count} 个已有结果，将跳过）")
    for f in pdf_files:
        size_mb = f.stat().st_size / (1024 * 1024)
        has_result = (
            CONFIG["skip_existing"]
            and ((SOURCE_DIR / f.stem / f"{f.stem}.md").exists()
         or (SOURCE_DIR / f.stem / f"{f.stem}_README.md").exists())
        )
        flag = "  ⏭️ 已有结果" if has_result else ""
        print(f"    📄 {f.name}  ({size_mb:.1f} MB){flag}")

    # ---- 选引擎 ----
    engine_key, engine_info = select_engine()

    if engine_key is None:
        show_recommendation()
        input("\n按 Enter 退出...")
        sys.exit(0)

    # ---- 检查引擎是否已安装 ----
    import_name_map = {
        "docling": "docling",
        "marker": "marker",
        "mineru": "magic_pdf",
    }
    try:
        __import__(import_name_map[engine_key])
    except ImportError:
        print(f"\n❌ 未安装 {engine_info['name']}")
        print(f"   请在虚拟环境中运行：{engine_info['install']}")
        input("\n按 Enter 退出...")
        sys.exit(1)

    print(f"\n✅ 引擎：{engine_info['name']}")

    # ---- 逐文件转换 ----
    success_list = []
    skip_list = []
    fail_list = []
    total_start = time.time()

    for i, pdf_path in enumerate(pdf_files, 1):
        output_dir = SOURCE_DIR / pdf_path.stem
        md_file = output_dir / f"{pdf_path.stem}.md"
        pdf_dest = output_dir / pdf_path.name

        print(f"\n{'─' * 50}")
        print(f"  [{i}/{len(pdf_files)}] {pdf_path.name}")

        # 分批模式下，用 README.md 的存在来判断是否已完成
        index_file = output_dir / f"{pdf_path.stem}_README.md"
        already_done = md_file.exists() or index_file.exists()

        if CONFIG["skip_existing"] and already_done:
            print(f"  ⏭️  跳过（已有结果）")
            skip_list.append(pdf_path.name)
            continue


        ok, plen = check_path_length(pdf_path)
        if not ok:
            print(f"  ❌ 路径过长（{plen} 字符），请缩短 PDF 文件名")
            fail_list.append((pdf_path.name, f"路径过长（{plen} 字符）"))
            continue

        output_dir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()

        try:
            engine_info["func"](pdf_path, output_dir, md_file)
            if pdf_dest != pdf_path:
                shutil.copy2(pdf_path, pdf_dest)
            generate_llms_txt(pdf_path.stem, output_dir, pdf_path.name)

            elapsed = time.time() - t0
            print(f"  ✅ 完成（{elapsed:.1f}s）")
            print(f"  📁 {output_dir.relative_to(SOURCE_DIR)}/")
            success_list.append(pdf_path.name)

        except MemoryError:
            elapsed = time.time() - t0
            print(f"  ❌ 内存不足（{elapsed:.1f}s）")
            fail_list.append((pdf_path.name, "内存不足（OOM）"))
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  ❌ 失败（{elapsed:.1f}s）：{e}")
            fail_list.append((pdf_path.name, str(e)))

    # ---- 汇总 ----
    total = time.time() - total_start
    print(f"\n{'=' * 58}")
    print(f"  转换总结")
    print(f"{'=' * 58}")
    print(f"  引擎：{engine_info['name']}")
    print(f"  ✅ 成功：{len(success_list)} 个")
    print(f"  ⏭️  跳过：{len(skip_list)} 个")
    print(f"  ❌ 失败：{len(fail_list)} 个")
    print(f"  ⏱️  总耗时：{total:.0f} 秒")
    print(f"  📂 输出：{SOURCE_DIR}")

    if fail_list:
        print(f"\n  失败详情：")
        for name, err in fail_list:
            print(f"  ❌ {name}")
            print(f"     {err}")

    if success_list:
        first_name = success_list[0]
        first_stem = Path(first_name).stem
        print(f"\n{'─' * 50}")
        print(f"  输出结构示例：")
        print(f"{'─' * 50}")
        print(f"""
  {SOURCE_DIR}/
    ├── {first_name}
    ├── {first_stem}/
    │   ├── {first_name}              ← PDF 备份
    │   ├── {first_stem}.md           ← 🔥 拖入 Chatbox
    │   ├── llms.txt                  ← AI 阅读引导
    │   └── images/                   ← 图片
    └── ...
""")

    print("  💡 上传方式：拖入 .md 文件 + images/ 文件夹即可。\n")
    input("按 Enter 退出...")


if __name__ == "__main__":
    main()
