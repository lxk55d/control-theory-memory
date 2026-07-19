#!/usr/bin/env python3
"""RapidOCR CLI - 一行命令识别图片中的文字

用法:
  rapidocr <图片路径>                      # 简单识别，输出纯文本
  rapidocr <图片路径> -v                   # 详细输出（含坐标、置信度）
  rapidocr <图片路径> -j                   # JSON 格式输出
  rapidocr <图片路径> -o result.txt        # 输出到文件
  rapidocr <图片路径1> <图片路径2> ...      # 批量识别
  rapidocr <目录路径>                       # 识别目录下所有图片

示例:
  rapidocr screenshot.png
  rapidocr ~/Downloads/invoice.jpg -j
  rapidocr ./images/ -o all_text.txt
"""

import argparse
import json
import sys
import os
from pathlib import Path

# 延迟导入，加速 --help
_engine = None
_engine_initialized = False

def get_engine():
    global _engine, _engine_initialized
    if _engine_initialized:
        return _engine
    # 初始化期间静默（RapidOCR 模块级 logger 在初始化时直接写 stderr）
    import contextlib
    import os, sys
    with open(os.devnull, 'w') as devnull:
        with contextlib.redirect_stderr(devnull):
            from rapidocr import RapidOCR
            _engine = RapidOCR()
    _engine_initialized = True
    return _engine

IMG_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp'}


def scan_images(paths):
    """展开路径列表为图片文件列表"""
    files = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for f in sorted(p.iterdir()):
                if f.suffix.lower() in IMG_EXTENSIONS:
                    files.append(str(f))
        elif p.is_file():
            if p.suffix.lower() in IMG_EXTENSIONS:
                files.append(str(p))
            else:
                print(f'⚠ 跳过非图片文件: {p}', file=sys.stderr)
    return files


def recognize(engine, img_path):
    """识别单张图片"""
    try:
        result = engine(img_path)
        return {
            'path': img_path,
            'txts': list(result.txts) if result.txts else [],
            'scores': [round(float(s), 4) for s in result.scores] if result.scores else [],
            'boxes': result.boxes.tolist() if result.boxes is not None else [],
            'elapse': round(result.elapse, 3) if result.elapse else 0,
        }
    except Exception as e:
        return {
            'path': img_path,
            'error': str(e),
            'txts': [],
            'scores': [],
        }


def main():
    parser = argparse.ArgumentParser(
        description='RapidOCR CLI - 离线 OCR 文字识别',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('paths', nargs='+', help='图片路径或目录')
    parser.add_argument('-v', '--verbose', action='store_true', help='详细输出（含坐标和置信度）')
    parser.add_argument('-j', '--json', action='store_true', help='JSON 格式输出')
    parser.add_argument('-o', '--output', help='输出到文件')
    parser.add_argument('-q', '--quiet', action='store_true', help='安静模式（不打印进度）')

    args = parser.parse_args()

    # 展开路径
    files = scan_images(args.paths)
    if not files:
        print('没有找到可识别的图片文件', file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f'📄 共 {len(files)} 张图片，正在识别...', file=sys.stderr)

    # 初始化引擎
    engine = get_engine()
    results = []

    for i, f in enumerate(files):
        if not args.quiet:
            print(f'  [{i+1}/{len(files)}] {os.path.basename(f)}...', file=sys.stderr, end=' ')
        r = recognize(engine, f)
        results.append(r)
        if not args.quiet:
            texts = ' | '.join(r['txts'][:3])
            if r.get('error'):
                print(f'❌ {r["error"]}', file=sys.stderr)
            elif texts:
                print(f'✅ {len(r["txts"])} 行', file=sys.stderr)
            else:
                print(f'⚠ 未识别到文字', file=sys.stderr)

    # 输出
    if args.json:
        output = json.dumps(results, ensure_ascii=False, indent=2)
    elif args.verbose:
        lines = []
        for r in results:
            lines.append(f'=== {r["path"]} ===')
            for txt, score, box in zip(r['txts'], r['scores'], r.get('boxes', [])):
                lines.append(f'  [{score:.2%}] {txt}')
                lines.append(f'    坐标: {box}')
            if not r['txts']:
                lines.append('  (无文字)')
            if r.get('error'):
                lines.append(f'  ❌ {r["error"]}')
        output = '\n'.join(lines)
    else:
        lines = []
        for r in results:
            for txt in r['txts']:
                lines.append(txt)
        output = '\n'.join(lines)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output + '\n')
        if not args.quiet:
            print(f'💾 已保存到 {args.output}', file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
