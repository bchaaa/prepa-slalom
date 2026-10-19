"""Génère les messages vocaux de l'appli avec la voix clonée Fish Audio (modèle actif de FixNow31).

  python voix/generer_voix.py          # crée les fichiers manquants dans voix/
  python voix/generer_voix.py --tout   # régénère tout

La clé FISH_API_KEY est lue dans FixNow31 (videos/moteur/.env), jamais copiée ici.
"""
import json, os, re, sys, time

import requests

ICI = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(ICI)
FIX = r'C:\Users\bapti\Documents\projet_code\FixNow31\fixnow31\videos\moteur'
API = 'https://api.fish.audio'
MODELE_TTS = 's2.1-pro-free'


def cle():
    if os.environ.get('FISH_API_KEY'):
        return os.environ['FISH_API_KEY']
    for ligne in open(os.path.join(FIX, '.env'), encoding='utf-8'):
        if ligne.startswith('FISH_API_KEY='):
            return ligne.split('=', 1)[1].strip()
    raise SystemExit('FISH_API_KEY introuvable')


def modele():
    return json.load(open(os.path.join(FIX, 'voix', 'fish.json'), encoding='utf-8'))['modele']


FIXES = {
    'go': "C'est parti !",
    'prep': 'Prépare-toi.',
    'jambe_g': 'Jambe gauche.',
    'l_jambe': 'Change de jambe.',
    'l_cote': 'Change de côté.',
    'l_tour': 'Fin du tour.',
    'l_bloc': 'Récup. Bloc suivant.',
    'l_exo': 'Exercice suivant.',
    'l_prep': 'Prépare-toi.',
    'l_trot': 'Trot.',
    'l_score': 'Récup. Retiens ton score.',
    'moitie': 'Moitié !',
    'dix': 'Dix secondes.',
    'fin_seance': 'Bravo ! Séance terminée.',
    'fin_exo': 'Exercice terminé.',
    'fin_test': 'Test terminé.',
}


def manifeste():
    html = open(os.path.join(SITE, 'index.html'), encoding='utf-8').read()
    clips = dict(FIXES)
    for id_, nom in re.findall(r'^([a-z_]+):\{n:"([^"]+)"', html, flags=re.M):
        clips[f'n_{id_}'] = nom + '.'
        clips[f'nx_{id_}'] = f'Ensuite : {nom}.'
    return clips


def dire(texte, sortie, k, m):
    corps = {'text': texte, 'reference_id': m, 'format': 'mp3', 'mp3_bitrate': 64, 'sample_rate': 44100,
             'temperature': 0.7, 'top_p': 0.7, 'latency': 'normal', 'normalize': True,
             'prosody': {'speed': 1.05, 'volume': 0}}
    for essai in range(3):
        r = requests.post(f'{API}/v1/tts', json=corps, timeout=120,
                          headers={'Authorization': f'Bearer {k}', 'model': MODELE_TTS})
        if r.status_code == 200 and len(r.content) > 1000:
            open(sortie, 'wb').write(r.content)
            return True
        if r.status_code in (401, 402, 403):
            raise SystemExit(f'Fish {r.status_code} : {r.text[:300]}')
        time.sleep(2)
    print('  échec', r.status_code, r.text[:200])
    return False


if __name__ == '__main__':
    tout = '--tout' in sys.argv
    clips, k, m = manifeste(), cle(), modele()
    print('modèle', m, '·', len(clips), 'messages')
    ok = 0
    for nom, texte in clips.items():
        sortie = os.path.join(ICI, nom + '.mp3')
        if os.path.exists(sortie) and not tout:
            ok += 1
            continue
        if dire(texte, sortie, k, m):
            ok += 1
            print('ok', nom, '·', texte)
    json.dump(sorted(clips), open(os.path.join(ICI, 'liste.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'terminé : {ok}/{len(clips)}')
