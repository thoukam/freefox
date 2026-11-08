[English](SECURITY.md) · **Français**

# Politique de sécurité

## Versions prises en charge

FreeFox est en développement actif. Les correctifs de sécurité sont publiés sur la dernière version
et sur `main`.

| Version | Prise en charge |
|---|---|
| 0.2.x | ✅ |
| < 0.2 | ❌ |

## Signaler une vulnérabilité

Merci de **ne pas ouvrir d'issue publique** pour un problème de sécurité.

Signalez-le en privé, soit via le
[signalement privé de vulnérabilité GitHub](https://github.com/thoukam/freefox/security/advisories/new),
soit par e-mail à **thoukamy@gmail.com**, avec :

- une description du problème et de son impact,
- les étapes pour le reproduire, ou une preuve de concept,
- la version de FreeFox, le backend et le mode de déploiement (systemd ou Docker).

Vous recevrez un accusé de réception sous **72 heures**. Nous vous tiendrons informé pendant la
correction et vous créditerons dans les notes de version si vous le souhaitez.

## Recommandations pour les opérateurs

- **Dashboard :** il n'a pas encore d'authentification. Liez-le à `127.0.0.1`, ou exposez-le
  uniquement sur un réseau de confiance, derrière un VPN ou un reverse proxy authentifié. Ne
  l'exposez jamais sur Internet.
- **Credentials :** gardez `secrets/`, les tokens OAuth et `/etc/freefox/aws.env` hors du contrôle
  de version, avec des permissions `0600`/`0640`. Les clés S3 sont volontairement refusées dans le YAML.
- **Base de la file :** `queue.db` contient des URI de session resumable qui peuvent donner un accès
  temporaire en écriture. Gardez-la sur un stockage local protégé.
- **TLS :** ne désactivez jamais la vérification des certificats. Utilisez `s3.ca_bundle` pour une
  autorité de certification privée.
