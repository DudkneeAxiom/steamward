// Restrained, believable personal names for soldiers. No fantasy naming.

const FIRST = [
  'Tomas', 'Bren', 'Alys', 'Garet', 'Mabel', 'Osric', 'Edda', 'Hale', 'Rowan', 'Petra',
  'Colm', 'Ivo', 'Marta', 'Aldous', 'Nel', 'Wat', 'Sable', 'Joss', 'Hugh', 'Tilda',
  'Piers', 'Agnes', 'Rolf', 'Ede', 'Simeon', 'Bess', 'Cort', 'Ida', 'Leof', 'Anselm',
];

const LAST = [
  'Wren', 'Calder', 'Marsh', 'Fletcher', 'Stone', 'Weir', 'Cooper', 'Hartley', 'Brook',
  'Tanner', 'Kells', 'Mercer', 'Ashdown', 'Colley', 'Reed', 'Farrow', 'Holt', 'Webb',
  'Sutton', 'Crane', 'Millward', 'Bray', 'Norrell', 'Pike', 'Garner', 'Thorne', 'Ward',
];

export function soldierName(rng) {
  return `${rng.pick(FIRST)} ${rng.pick(LAST)}`;
}
