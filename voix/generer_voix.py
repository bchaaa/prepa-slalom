"""Messages vocaux de l'appli avec la voix finale de Baptiste (Fish Audio, réglages du 22/10/26).

Réglages (Documents/VOIX-BAPTISTE-REGLAGES.md) : clone v4, balise [excited], temperature 0.9,
top_p 0.9, chunk_length 300, normalize false, vitesse 1.0, texte écrit comme on parle.
Pour chaque message : plusieurs prises, contrôle par transcription (faster-whisper),
on garde la plus fidèle, puis silences coupés et volume normalisé à -16 LUFS (crête -1,5 dB).

À lancer avec le Python de FixNow31 (il a faster-whisper) :
  ...\\FixNow31\\fixnow31\\videos\\moteur\\.venv\\Scripts\\python.exe voix/generer_voix.py          # manquants
  ...\\FixNow31\\fixnow31\\videos\\moteur\\.venv\\Scripts\\python.exe voix/generer_voix.py --tout   # tout

La clé FISH_API_KEY est lue dans FixNow31 (videos/moteur/.env), jamais copiée ici.
"""
import difflib, json, os, re, subprocess, sys, tempfile, time, unicodedata

import requests

ICI = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(ICI)
FIX = r'C:\Users\bapti\Documents\projet_code\FixNow31\fixnow31\videos\moteur'
API = 'https://api.fish.audio'
MODELE_TTS = 's2.1-pro-free'
CLONE = '3c491d8ae3c5479c9a8a1efa952655a5'  # « Baptiste FixNow31 v4 », voix finale du 22/10/26
REGLAGES = {'temperature': 0.9, 'top_p': 0.9, 'chunk_length': 300, 'normalize': False,
            'latency': 'normal', 'prosody': {'speed': 1.0, 'volume': 0}}
PRISES, PRISES_MAX, SEUIL = 3, 6, 0.86
WHISPER = 'small'


def cle():
    if os.environ.get('FISH_API_KEY'):
        return os.environ['FISH_API_KEY']
    for ligne in open(os.path.join(FIX, '.env'), encoding='utf-8'):
        if ligne.startswith('FISH_API_KEY='):
            return ligne.split('=', 1)[1].strip()
    raise SystemExit('FISH_API_KEY introuvable')


# Textes écrits pour l'oreille : phrases courtes, points d'exclamation, nombres en lettres.
FIXES = {
    'go': "C'est parti !",
    'prep': 'Prépare-toi !',
    'jambe_g': 'Jambe gauche !',
    'l_jambe': 'Change de jambe !',
    'l_cote': 'Change de côté !',
    'l_tour': 'Fin du tour !',
    'l_bloc': 'Récup ! Bloc suivant !',
    'l_exo': 'Exercice suivant !',
    'l_prep': 'Prépare-toi !',
    'l_trot': 'Trottine tranquille !',
    'l_score': 'Récup ! Retiens bien ton score !',
    'moitie': "T'es à la moitié !",
    'dix': 'Plus que dix secondes !',
    'fin_seance': 'Bravo ! Séance terminée !',
    'fin_exo': 'Exercice terminé ! Bien joué !',
    'fin_test': 'Test terminé ! Note ton score !',
}
DIT = {'Fractionné 30/30': 'Fractionné trente trente', 'Gainage latéral + rotation': 'Gainage latéral avec rotation'}


def parle(nom):
    """Nom d'exercice tel qu'on le dit : « 1 jambe » → « sur une jambe », « + » → « et »."""
    if nom in DIT:
        return DIT[nom]
    nom = nom.replace(' 1 jambe', ' sur une jambe').replace(' + ', ' et ')
    return re.sub(r'(?<=\w)-(?=\w)', ' ', nom)


def manifeste():
    html = open(os.path.join(SITE, 'index.html'), encoding='utf-8').read()
    clips = dict(FIXES)
    for id_, nom in re.findall(r'^([a-z0-9_]+):\{n:"([^"]+)"', html, flags=re.M):
        dit = parle(nom)
        clips[f'n_{id_}'] = dit + ' !'
        clips[f'nx_{id_}'] = f'Ensuite {dit[0].lower() + dit[1:]} !'
    return clips


# --- contrôle par transcription ---
CHIFFRES = {'1': 'un', '10': 'dix', '30': 'trente', '2': 'deux'}


def norme(t):
    t = unicodedata.normalize('NFD', t.lower())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    t = re.sub(r'\[[^\]]*\]', ' ', t)
    t = re.sub(r"[^a-z0-9 ]", ' ', t.replace("'", ' '))
    return ' '.join(CHIFFRES.get(m, m) for m in t.split())


_whisper = None


def transcrit(wav):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(WHISPER, device='cpu', compute_type='int8')
    segs, _ = _whisper.transcribe(wav, language='fr', beam_size=5, condition_on_previous_text=False, vad_filter=False)
    return ' '.join(s.text for s in segs).strip()


def duree(wav):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', wav],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 99.0


def prise(texte, sortie, k):
    corps = dict(REGLAGES, text='[excited] ' + texte, reference_id=CLONE, format='wav', sample_rate=44100)
    for essai in range(4):
        try:
            r = requests.post(f'{API}/v1/tts', json=corps, timeout=120,
                              headers={'Authorization': f'Bearer {k}', 'model': MODELE_TTS})
        except requests.RequestException as e:
            print('  réseau', e)
            time.sleep(3)
            continue
        if r.status_code == 200 and len(r.content) > 2000:
            open(sortie, 'wb').write(r.content)
            return True
        if r.status_code in (401, 402, 403):
            raise SystemExit(f'Fish {r.status_code} : {r.text[:300]}')
        time.sleep(3 + 3 * essai)
    return False


def finalise(wav, mp3):
    """Coupe les silences de début et de fin, normalise à -16 LUFS (crête -1,5 dB), encode en MP3."""
    filtre = ('silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.04,areverse,'
              'silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse,'
              'apad=pad_dur=0.05,loudnorm=I=-16:TP=-1.5:LRA=11')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wav, '-af', filtre, '-ac', '1', '-ar', '44100',
                    '-c:a', 'libmp3lame', '-b:a', '80k', mp3], check=True)


def meilleure(nom, texte, k, dossier):
    attendu, prises, pannes = norme(texte), [], 0
    while len(prises) < PRISES_MAX:
        n = len(prises) + 1
        wav = os.path.join(dossier, f'{nom}-{n}.wav')
        if not prise(texte, wav, k):
            pannes += 1
            if len(prises) >= PRISES or pannes > 3:
                break
            time.sleep(60)  # réseau ou limite Fish : on patiente puis on réessaie
            continue
        dit = transcrit(wav)
        score = difflib.SequenceMatcher(None, attendu, norme(dit)).ratio()
        prises.append({'wav': wav, 'score': round(score, 3), 'dit': dit, 'duree': round(duree(wav), 2)})
        if len(prises) >= PRISES and max(p['score'] for p in prises) >= SEUIL:
            break
    if len(prises) < PRISES:
        return None  # pas assez de prises : on ne fige rien, la prochaine relance le refera
    top = max(p['score'] for p in prises)
    # à fidélité quasi égale, la prise la plus courte (moins d'hésitations)
    return min((p for p in prises if p['score'] >= top - 0.03), key=lambda p: p['duree']), prises


if __name__ == '__main__':
    tout = '--tout' in sys.argv
    faibles_seuls = '--faibles' in sys.argv  # refait les messages sous le seuil : plus de prises, Whisper plus précis
    if faibles_seuls:
        PRISES, PRISES_MAX, WHISPER = 5, 10, 'medium'
    clips, k = manifeste(), cle()
    rapport_f = os.path.join(ICI, 'rapport.json')
    rapport = {} if tout or not os.path.exists(rapport_f) else json.load(open(rapport_f, encoding='utf-8'))
    print('clone', CLONE, '·', len(clips), 'messages', flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        for nom, texte in clips.items():
            mp3 = os.path.join(ICI, nom + '.mp3')
            if not tout and os.path.exists(mp3) and nom in rapport and not (faibles_seuls and rapport[nom]['score'] < SEUIL):
                continue
            if faibles_seuls and nom in rapport and rapport[nom]['score'] >= SEUIL:
                continue
            res = meilleure(nom, texte, k, tmp)
            if not res:
                print('ÉCHEC', nom, flush=True)
                continue
            choix, prises = res
            if nom in rapport and choix['score'] < rapport[nom]['score'] and os.path.exists(mp3):
                print("garde l'ancienne", nom, rapport[nom]['score'], flush=True)
                continue
            finalise(choix['wav'], mp3)
            rapport[nom] = {'texte': texte, 'score': choix['score'], 'entendu': choix['dit'],
                            'prises': len(prises), 'scores': [p['score'] for p in prises]}
            print(f"{'ok ' if choix['score'] >= SEUIL else 'À ÉCOUTER'} {nom} · {choix['score']} · {texte} → {choix['dit']}", flush=True)
            json.dump(rapport, open(rapport_f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(sorted(clips), open(os.path.join(ICI, 'liste.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    faibles = [n for n, r in rapport.items() if r['score'] < SEUIL]
    print(f'terminé : {len(rapport)}/{len(clips)} · à écouter : {", ".join(faibles) or "aucun"}', flush=True)
