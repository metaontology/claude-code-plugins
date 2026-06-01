import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")

text = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()

lines = text.splitlines()
result = "\n".join(line.rstrip() for line in lines)

output_path = "tmp/clipboard.txt"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(result)

print(f"저장 완료: {output_path}")
