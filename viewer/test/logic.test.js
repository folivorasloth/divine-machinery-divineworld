// Testes leves das regras do viewer (sem navegador): `npm test`
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  animForAction, pickClip, normalizeClipName, shortenBubble, bubbleDuration, gridLayout, gridPositions,
  worldHours, daylight, rainIntensity, teleportAppearAt, hatKind, accessoryKinds, outfitKind, gaitKind, DEFAULT_VISUAL,
} from '../src/logic.js';

test('ação -> animação vem do world.yaml; sem ação = idle; andando = walk', () => {
  const v = { action_animation: { brigar: 'fight', rezar: 'pray', esquisita: 'voar' } };
  assert.equal(animForAction('brigar', false, v), 'fight');
  assert.equal(animForAction('rezar', false, v), 'pray');
  assert.equal(animForAction('nada', false, v), 'idle');
  assert.equal(animForAction('esquisita', false, v), 'idle'); // nome inválido não quebra
  assert.equal(animForAction(null, false, v), 'idle');
  assert.equal(animForAction('rezar', true, v), 'walk');
});

test('clipe do .glb por nome, com prefixo do Blender e substitutas', () => {
  assert.equal(normalizeClipName('Armature|Walk_01'), 'walk01');
  const names = ['Armature|Idle', 'Armature|Walk_01', 'Dance'];
  assert.deepEqual(pickClip(names, 'walk'), { clip: 'Armature|Walk_01', name: 'walk', exact: true });
  assert.deepEqual(pickClip(names, 'dance'), { clip: 'Dance', name: 'dance', exact: true });
  // falta "fight": tenta as substitutas e cai no idle, marcando que precisa de procedural
  assert.deepEqual(pickClip(names, 'fight', { fight: ['work', 'idle'] }), { clip: 'Armature|Idle', name: 'idle', exact: false });
  assert.deepEqual(pickClip([], 'walk'), { clip: null, name: null, exact: false });
});

test('balão: tira o nome e as aspas, encurta, duração proporcional', () => {
  assert.equal(shortenBubble('A Cozinheira: "Come que esfria!"', 'A Cozinheira'), 'Come que esfria!');
  assert.equal(shortenBubble('O Palhaço tropeça.', 'O Palhaço'), 'O Palhaço tropeça.');
  const long = shortenBubble('palavra '.repeat(40), null, 40);
  assert.ok(long.length <= 40 && long.endsWith('…'));
  const c = DEFAULT_VISUAL.bubbles;
  assert.ok(bubbleDuration('oi', c) < bubbleDuration('uma frase bem mais comprida do que oi', c));
  assert.equal(bubbleDuration('x'.repeat(1000), c), c.max_seconds);
});

test('grade: telas largas ficam com mais colunas; posições centradas', () => {
  assert.deepEqual(gridLayout(11, 16 / 9), { cols: 4, rows: 3 });
  assert.deepEqual(gridLayout(2, 16 / 9), { cols: 2, rows: 1 });
  assert.deepEqual(gridLayout(1, 1), { cols: 1, rows: 1 });
  const pos = gridPositions(['a', 'b', 'c'], 2, 10, 2);
  assert.equal(pos.a.x, -6); assert.equal(pos.b.x, 6); assert.equal(pos.c.x, 0); // a última linha centraliza
});

test('hora do mundo, dia e noite', () => {
  assert.equal(worldHours('2026-11-10T09:30:00-03:00'), 9.5);
  assert.equal(daylight(12), 1);
  assert.equal(daylight(0), 0);
  assert.ok(daylight(6) > 0 && daylight(6) < 1);
});

test('chuva: no funeral (clima forçado) é sempre forte', () => {
  assert.equal(rainIntensity('limpo', null, false), 0);
  assert.ok(rainIntensity('garoa', null, false) < rainIntensity('chuva', null, false));
  assert.equal(rainIntensity('chuva', 'funeral', false), 1);
  assert.equal(rainIntensity('garoa', null, true), 1);
});

test('túnel: aparece quando a luz chega E a simulação diz que saiu', () => {
  assert.equal(teleportAppearAt(1000, 4, 2000), 5000); // a luz demora mais
  assert.equal(teleportAppearAt(1000, 0.5, 2000), 2000); // a simulação demora mais
  assert.equal(teleportAppearAt(1000, 4, null), null); // ainda no túnel
  assert.equal(teleportAppearAt(null, 4, 3000), 3000); // tela abriu no meio do caminho
});

test('aparência do YAML vira peças reconhecíveis', () => {
  assert.equal(hatKind('chapéu de palha'), 'straw');
  assert.equal(hatKind('chapéu de chef torto'), 'chef');
  assert.equal(hatKind('chapéu de guizos'), 'jester');
  assert.equal(hatKind('nenhum'), null);
  assert.deepEqual(accessoryKinds('nariz vermelho'), ['nose']);
  assert.deepEqual(accessoryKinds('apito e régua'), ['whistle']);
  assert.equal(outfitKind('Batina preta comprida demais', 'crucifixo enorme'), 'cassock');
  assert.equal(outfitKind('Vestido longo exagerado', 'leque'), 'dress');
  assert.equal(gaitKind('Saltitando e dando estrelinhas.'), 'hop');
  assert.equal(gaitKind('Devagar e gingado.'), 'swing');
  assert.equal(gaitKind('De skate. Cai em toda escada.'), 'skate');
});
