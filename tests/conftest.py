import sys
from pathlib import Path

# Permite importar core/ e utils/ rodando "pytest" na pasta do projeto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
