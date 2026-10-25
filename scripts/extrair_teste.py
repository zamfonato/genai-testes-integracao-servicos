"""Extrai o arquivo de teste (bloco ```python com `def test_`) de uma resposta da LLM.

Uso: python -m scripts.extrair_teste saidas/rodada-1/p1-zero-shot-contrato.md tests/geradas/test_p1_contrato.py
"""

import re
import sys
from pathlib import Path

resposta, destino = Path(sys.argv[1]), Path(sys.argv[2])
blocos = re.findall(r"```python\n(.*?)```", resposta.read_text(encoding="utf-8"), flags=re.S)
testes = [b for b in blocos if "def test_" in b]
if len(testes) != 1:
    sys.exit(f"esperava 1 bloco de teste, achei {len(testes)}")
destino.parent.mkdir(parents=True, exist_ok=True)
destino.write_text(testes[0], encoding="utf-8")
print(f"{destino}: {testes[0].count('def test_')} testes")
