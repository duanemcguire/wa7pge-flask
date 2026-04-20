const MORSE_TABLE = {
  A:'.-',   B:'-...', C:'-.-.', D:'-..',  E:'.',    F:'..-.',
  G:'--.',  H:'....', I:'..',   J:'.---', K:'-.-',  L:'.-..',
  M:'--',   N:'-.',   O:'---',  P:'.--.', Q:'--.-', R:'.-.',
  S:'...',  T:'-',    U:'..-',  V:'...-', W:'.--',  X:'-..-',
  Y:'-.--', Z:'--..',
  '0':'-----','1':'.----','2':'..---','3':'...--','4':'....-',
  '5':'.....','6':'-....','7':'--...','8':'---..','9':'----.',
  '.':'.-.-.-', ',':'--..--', '?':'..--..', "'":'.----.',
  '!':'-.-.--', '/':'-..-.', '(':'-.--.', ')':'-.--.-',
  '&':'.-...', ':':'---...', ';':'-.-.-.', '=':'-...-',
  '+':'.-.-.', '-':'-....-', '"':'.-..-.', '@':'.--.-.'
};

function ditMs(wpm) {
  return 1200 / wpm;
}

// Returns { intervals: [{start, end}], totalMs } for tone-on periods only.
// start/end are in milliseconds from t=0.
// wordSpacingRatio scales the standard 7-unit word gap (1.0 = exact standard).
function textToTiming(text, wpm, wordSpacingRatio = 1.0) {
  const dit = ditMs(wpm);
  const dah = 3 * dit;
  const elemGap = dit;
  const charGap = 3 * dit;
  const wordGap = 7 * dit * wordSpacingRatio;

  const intervals = [];
  let t = 0;
  const words = text.toUpperCase().split(/\s+/).filter(Boolean);

  for (let wi = 0; wi < words.length; wi++) {
    const word = words[wi];
    for (let ci = 0; ci < word.length; ci++) {
      const code = MORSE_TABLE[word[ci]];
      if (!code) continue;
      for (let ei = 0; ei < code.length; ei++) {
        const dur = code[ei] === '.' ? dit : dah;
        intervals.push({ start: t, end: t + dur });
        t += dur;
        if (ei < code.length - 1) t += elemGap;
      }
      if (ci < word.length - 1) t += charGap;
    }
    if (wi < words.length - 1) t += wordGap;
  }

  return { intervals, totalMs: t };
}
