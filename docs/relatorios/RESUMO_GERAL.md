# Resumo geral — Divine Machinery: o Mundo Vivo

**Data:** 2026-11-10 · **Repositório:** `folivorasloth/divine-machinery-divineworld` (branch `main`)

As 7 fases (0 a 6) foram executadas em ordem, cada uma por um subagente com contexto novo e revisada pelo orquestrador: testes rodados de novo, simulação de verdade com seeds diferentes das do subagente e conferência de cada critério de aceite. A tabela de cada revisão está na seção "Revisão do orquestrador" do relatório da fase.

## Estado de cada fase

| Fase | Estado | Destaques verificados na revisão | Relatório |
|---|---|---|---|
| 0 · Preparação | ✅ concluída | `tools.validate` com 0 erros; renomear o Palhaço só no `nome:` não quebra nada; arquitetura das fases 1–5 escrita | [FASE_0](FASE_0.md) |
| 1 · Núcleo | ✅ concluída | `--speed 600` por 5 min reais (~2 dias) sem erro; todos dormem, comem, trabalham; Mike perambula; sino 06/12/18 h | [FASE_1](FASE_1.md) |
| 2 · Sociedade | ✅ concluída | semana (seed 777): 43 discussões, 5 brigas, 27 pazes, 87 fofocas, 13 prisões, 36 rituais, festas organizadas por NPCs | [FASE_2](FASE_2.md) |
| 3 · Vida, morte e Diretor | ✅ concluída | 30 dias (seed 314): 3 mortes, 3 nascimentos, sucessão da Médium, funeral com chuva; relatório de variedade sem alertas | [FASE_3](FASE_3.md) |
| 4 · Criador e API | ✅ concluída | `docker compose up`: API e Chat web ao vivo; `chefe "reconstruam a ferraria"` → mutirão reconstruiu pelo comportamento; sem MQTT/Ollama tudo segue | [FASE_4](FASE_4.md) |
| 5 · Visual 3D | ✅ concluída | duas abas, o Técnico atravessa o túnel e aparece ~4 s depois na outra tela; `.glb` troca o Chefe sem código; 21 prints | [FASE_5](FASE_5.md) |
| 6 · Polimento e guias | ✅ concluída | renomear pelo guia 01 aparece no Chat e no 3D sem reiniciar; 60 dias sem erro; 10 guias; `recarregar`; robustez | [FASE_6](FASE_6.md) |

Números finais: 199 testes Python passando, 8 testes do viewer, `npm run build` ok, `tools.validate` com 0 erros.

## Pendências priorizadas

1. **Rodar no homelab de verdade** — o `docker compose up -d --build` padrão não foi provado no sandbox (a imagem precisou do certificado do proxy e de um espelho da imagem base); MQTT dentro do Docker, Ollama real e telas físicas também não existem aqui. Guia 09.
2. **Automação do WLED** (`leds/tunnel` → fita) — receita no guia 07; precisa da fita instalada para calibrar.
3. **Desempenho em hardware velho** — o viewer só foi medido com renderização por software (20–31 FPS). Limite de FPS/qualidade por tela já existe no `world.yaml`.
4. **Técnicos trabalhando só por problema real do homelab** — decidir o que fazem quando nada está quebrado.
5. **Luz real do quarto (pegadinha do Palhaço) e instrumento do Músico** — falta decidir o tópico MQTT (guia 08).
6. **Pendências criativas da bible** — nomes definitivos, o personagem raro do Criador (ficha em branco), bestiário de verdade (hoje 5 criaturas provisórias), sons por lugar.
7. **Relíquias do Esquisito como itens de ritual**; criaturas com modelo 3D próprio; animação de cenário `.glb`.
8. **Pequenos:** quem é solto dormindo acorda "na Prisão"; falas antigas com `{@priest}` citam o Padre original depois de uma sucessão; chuva cai também em lugares internos no viewer.

## Decisões que valem conferir (registradas nos relatórios)
- Lugar extra "O Campo" (`fields`) para os Cowboys trabalharem (F0).
- Não existe Carteiro na bible: quem espalha fofoca é o traço `fofoqueiro` (F2).
- Simulação e servidor num processo só (F4), um serviço `world` no Docker.
- Personagens desenhados 1,3× no viewer para ficarem legíveis (F5).
- Regra de no máximo 2 mortes sorteadas em 7 dias (`limites.max_mortes_em_7_dias`, F6), configurável no YAML.

## Por onde começar
README → `docs/guias/01` (renomear) → `07` (telas) → `09` (rodar e manter) → `10` (comandos do Criador).
