#!/usr/bin/env python3
"""
提取并查看回测结果zip文件的内容
"""

import os
import zipfile

# 配置
zip_file_path = (
    "d:/quantsys/ai_collaboration/backtest_results/backtest-result-2026-01-06_20-15-47.zip"
)
extract_dir = "d:/quantsys/ai_collaboration/temp_unzip"

# 创建提取目录
os.makedirs(extract_dir, exist_ok=True)

# 提取zip文件
print(f"提取zip文件: {zip_file_path}")
with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
    zip_ref.extractall(extract_dir)

# 列出提取的文件
print("\n提取的文件:")
for root, dirs, files in os.walk(extract_dir):
    for file in files:
        file_path = os.path.join(root, file)
        print(f"   - {file_path}")

        # 查看JSON文件内容
        if file.endswith(".json"):
            print(f"\n{file} 内容:")
            with open(file_path) as f:
                content = f.read()
                print(content[:500])  # 只显示前500个字符
                if len(content) > 500:
                    print("...")

        # 查看CSV文件内容
        elif file.endswith(".csv"):
            print(f"\n{file} 内容:")
            with open(file_path) as f:
                lines = f.readlines()
                print("\n".join(lines[:10]))  # 只显示前10行
                if len(lines) > 10:
                    print("...")

print(f"\n提取完成，文件已保存到: {extract_dir}")
