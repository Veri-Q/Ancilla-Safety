# Grover 量子搜索电路生成器

生成 Grover 量子搜索算法的 QASM2 电路文件。

## 使用方法

### 命令行生成

```bash
# 基本用法（生成 n=5 的 dirty ancilla 电路）
python grover_gen.py 5

# 指定目标状态
python grover_gen.py 5 -m 3        # 搜索状态 3
python grover_gen.py 5 --marked-item 3

# 使用 clean ancilla（默认是 dirty）
python grover_gen.py 5 --clean
python grover_gen.py 5 -c

# 指定输出文件
python grover_gen.py 5 -o my_circuit.qasm
python grover_gen.py 5 --output my_circuit.qasm
```

### 组合参数

```bash
# clean ancilla + 指定目标状态 + 指定输出
python grover_gen.py 5 -c -m 7 -o grover5_target7.qasm

# dirty ancilla（默认）+ n=10 + 目标状态 0
python grover_gen.py 10
```

### Python 调用

```python
from grover_gen import generate_grover

# 生成电路
generate_grover(n=5, marked_item=0, dirty=True, output="grover5.qasm")

# 使用 clean ancilla
generate_grover(n=5, marked_item=3, dirty=False, output="grover5_clean.qasm")
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `n` | 量子比特数（工作寄存器大小） | 必需 |
| `-m, --marked-item` | 目标搜索状态（整数） | 0 |
| `-d, --dirty` | 使用 dirty ancilla | True（默认） |
| `-c, --clean` | 使用 clean ancilla | False |
| `-o, --output` | 输出文件路径 | `grover_n{n}_{anc_type}_{marked_item}.qasm` |

## 输出文件格式

输出为 QASM2 格式，包含以下寄存器：
- `r[n]` - 工作寄存器
- `ph_ase[1]` - 相位量子比特
- `anc[n-2]` - 辅助量子比特（n > 2 时）

## 电路结构

每轮 Grover 迭代包含：
1. Oracle（标记目标状态）
2. Grover 扩散算子（使用 MCX 门）

迭代次数为 ⌊π/4 × √(2^n)⌋
