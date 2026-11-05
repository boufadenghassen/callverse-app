"""Diagnostic : ta carte graphique peut-elle faire tourner VoxCPM ?   python check_gpu.py"""
import sys
try:
    import torch
except ImportError:
    sys.exit("PyTorch n'est pas installé dans cet environnement.")

print(f"PyTorch {torch.__version__} | build CUDA : {torch.version.cuda}")
if not torch.cuda.is_available():
    print("CUDA indisponible : PyTorch ne voit pas la carte (version CPU installée, pilote ou version incompatible).")
    sys.exit(1)

i = torch.cuda.current_device()
name, cap = torch.cuda.get_device_name(i), torch.cuda.get_device_capability(i)
free, total = torch.cuda.mem_get_info()
print(f"Carte : {name} | capacité de calcul {cap[0]}.{cap[1]} | VRAM libre {free/2**30:.1f} / {total/2**30:.1f} Go")
for dt in (torch.float16, torch.bfloat16):
    try:
        x = torch.randn(256, 256, device="cuda", dtype=dt)
        (x @ x).sum().item()
        print(f"  calcul en {str(dt).split('.')[-1]} : OK")
    except Exception as e:
        print(f"  calcul en {str(dt).split('.')[-1]} : ECHEC ({type(e).__name__}: {str(e)[:100]})")
if free / 2**30 < 7.5:
    print("\nATTENTION : VoxCPM2 demande environ 8 Go de VRAM. Il en reste moins : arrête Ollama (ollama stop <modele>)"
          " et ferme les applications gourmandes, ou le chargement échouera.")
