"""Comandos do Criador pela linha de comando (fala com a API do servidor).

    python -m tools.cli chefe "reconstruam a ferraria"
    python -m tools.cli medium "a lua quer uma festa"
    python -m tools.cli reviver blacksmith
    python -m tools.cli nascer alegre curioso
    python -m tools.cli pausar | continuar | velocidade 60
    python -m tools.cli status
    python -m tools.cli quem clown
    python -m tools.cli recarregar                 # aplica as mudanças de data/ sem reiniciar
    python -m tools.cli chat --personagem clown --limite 20     # últimas falas (histórico)
    python -m tools.cli --url http://homelab.local:8000 status

O endereço vem de --url, da variável DW_API_URL, ou de http://localhost:<servidor.porta>.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx


def default_url() -> str:
    if os.environ.get("DW_API_URL"):
        return os.environ["DW_API_URL"].rstrip("/")
    return f"http://localhost:{os.environ.get('DW_SERVER_PORT', '8000')}"


def print_status(s: dict) -> None:
    print(f"Hora do mundo: {s['hora']} ({s['periodo']}{', noite' if s['noite'] else ''}) · clima: {s['clima']}")
    print(f"Tensão: {s['tensao']:.0f} · velocidade {s['velocidade']:g}× · {'PAUSADO' if s['pausado'] else 'andando'}"
          f" · {s['populacao']} vivos · ticks {s['ticks']}")
    if s["mortos"]:
        print("Mortos: " + ", ".join(s["mortos"]))
    if s["nevoa"]:
        print("Na névoa: " + ", ".join(s["nevoa"]))
    for o in s["ordens"]:
        r = o["respostas"]
        print(f"  ordem #{o['id']} ({o['canal']}): \"{o['texto']}\" -> {o['entendeu']} [{o['como']}] · {o['estado']}"
              f"{' · entendeu ERRADO' if o['errou'] else ''} · aceitam {r['aceita']}, atrasam {r['atrasa']}, "
              f"resistem {r['resiste']}" + (f" · construíram: {', '.join(o['construiram'])}" if o["construiram"] else ""))
    for d in s["decretos"]:
        print(f"  decreto: {d['acao']} {d['modo']} até {d['ate']}")
    for t in s["assuntos"]:
        print(f"  assunto do momento: {t['assunto']} ({t['sobre'] or '—'}) até {t['ate']}")
    p = s["presenca"]
    print(f"Presença no quarto: {p['pessoas']} ({'sim' if p['ativa'] else 'não'}) · última Aparição: "
          f"{p['ultima_aparicao'] or 'nunca'}")
    llm = s["llm"]
    print(f"LLM: {'no ar' if llm.get('no_ar') else 'fora (templates)'}")


def print_sheet(f: dict) -> None:
    print(f"{f['nome']} ({f['id']}) · {'vivo' if f['vivo'] else 'MORTO'} · {f['profissao']} · facção {f['faccao']}")
    print(f"Traços: {', '.join(f['tracos'])}" + (f" (ganhou: {', '.join(f['tracos_ganhos'])})" if f["tracos_ganhos"] else ""))
    print(f"Onde: {f['lugar_nome']} · fazendo: {f['acao'] or '—'}" + (f" (com {f['alvo']})" if f["alvo"] else "")
          + (f" · indo {f['plano']['acao']} em {f['plano']['destino']}" if f["plano"] else ""))
    print("Necessidades: " + ", ".join(f"{k} {v:.0f}" for k, v in f["necessidades"].items()) + f" · humor: {f['humor']}")
    if f["preso"] or f["no_limbo"] or f["luto"]:
        print(f"Preso: {f['preso']} · Limbo: {f['no_limbo']} · luto: {f['luto']}")
    print("Memórias:")
    for m in f["memorias"]:
        print(f"  - {m['frase']} (força {m['intensidade']}{', para sempre' if m['permanente'] else ''}"
              + (f", ouviu de {m['ouviu_de']}" if m["ouviu_de"] else "") + ")")
    print("Gosta mais de: " + ", ".join(f"{r['nome']} {r['afinidade']:+.0f}" for r in f["gosta_mais"]))
    print("Gosta menos de: " + ", ".join(f"{r['nome']} {r['afinidade']:+.0f}" for r in f["gosta_menos"]))
    if f["objetivos"]:
        print("Objetivos ativos: " + ", ".join(f"{g['acao']}@{g['lugar'] or 'qualquer'} ×{g['bonus']}" for g in f["objetivos"]))
    if f["ultima_decisao"]:
        print("Última decisão: " + f["ultima_decisao"])


def print_reload(res: dict) -> None:
    if not res.get("ok"):
        print("NÃO recarregou: os YAML têm erro. O mundo continua com a versão anterior.")
        for e in res.get("errors", []):
            print("  - " + e)
        if res.get("more_errors"):
            print(f"  ... e mais {res['more_errors']}. Rode: python -m tools.validate")
        return
    print(f"Recarregado: {res['characters']} personagens, {res['places']} lugares, {res['actions']} ações, "
          f"{res['lines']} falas.")
    for r in res.get("renamed", []):
        print(f"  {r['id']}: {r['old']} -> {r['new']}")
    if res.get("added"):
        print("  novos no mundo: " + ", ".join(res["added"]))
    if res.get("kept_old"):
        print("  sem arquivo (continuam com a versão antiga): " + ", ".join(res["kept_old"]))
    if res.get("restart_needed"):
        print("  só vale depois de reiniciar o servidor: " + ", ".join(res["restart_needed"]))
    for w in res.get("warnings", []):
        print("  aviso: " + w)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Comandos do Criador (via API).")
    p.add_argument("--url", default=default_url(), help="endereço do servidor (padrão: DW_API_URL ou localhost)")
    p.add_argument("--json", action="store_true", help="mostra a resposta crua (JSON)")
    p.add_argument("--personagem", default=None, help="(chat) filtra por personagem")
    p.add_argument("--lugar", default=None, help="(chat) filtra por lugar")
    p.add_argument("--tipo", default=None, help="(chat) filtra por categoria (briga, morte, criador...)")
    p.add_argument("--limite", type=int, default=20, help="(chat) quantas linhas")
    p.add_argument("comando", help="chefe, medium, reviver, nascer, pausar, continuar, velocidade, status, quem, recarregar, chat...")
    p.add_argument("arg", nargs="*", help="o resto (a ordem, a mensagem, o id...)")
    args = p.parse_args(argv)
    arg = " ".join(args.arg)
    try:
        with httpx.Client(base_url=args.url, timeout=10) as c:
            if args.comando == "chat":
                q = {"limit": args.limite}
                for k, v in (("character", args.personagem), ("place", args.lugar), ("tag", args.tipo)):
                    if v:
                        q[k] = v
                r = c.get("/api/chat", params=q)
                r.raise_for_status()
                for ev in reversed(r.json()["events"]):
                    if ev.get("text_rendered"):
                        print(f"[{ev['ts'][8:10]}/{ev['ts'][5:7]} {ev['ts'][11:16]}] {ev['text_rendered']}")
                return 0
            r = c.post("/api/commands", json={"cmd": args.comando, "arg": arg})
    except httpx.HTTPError as exc:
        print(f"Não consegui falar com o servidor em {args.url}: {exc}\n"
              "Ele está rodando? (python -m server, ou docker compose up)", file=sys.stderr)
        return 2
    if r.status_code >= 400:
        print(r.json().get("detail", r.text), file=sys.stderr)
        return 1
    body = r.json()
    res = body.get("result")
    if args.json or res is None:
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return 0
    if args.comando == "status" and res.get("ok"):
        print_status(res["status"])
    elif args.comando == "quem" and res.get("ok"):
        print_sheet(res["sheet"])
    elif args.comando == "recarregar":
        print_reload(res)
    else:
        print(("ok: " if res.get("ok") else "não: ") + json.dumps({k: v for k, v in res.items() if k != "ok"},
                                                                  ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
