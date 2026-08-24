# Slack-oppsett

Slack blir brukerflaten. Undersøkelsen kjører på Macen, resultatet sendes bare som en
direktemelding til den som bestilte det, og rapporten lagres i det private runtime-repoet.
Ingen mål sendes til det offentlige repoet eller til GitHub Actions.

## Én gangs oppsett

1. Åpne Slacks side for å opprette en app og velg **From a manifest**.
2. Velg riktig arbeidsområde og lim inn innholdet i `slack-app-manifest.yml`.
3. Opprett appen og installer den i arbeidsområdet.
4. Under **Basic Information**, opprett et app-token med tillatelsen
   `connections:write`. Dette tokenet starter med `xapp-`.
5. Under **OAuth & Permissions**, kopier bot-tokenet. Det starter med `xoxb-`.
6. Kjør lokalt:

   ```bash
   wi slack setup --runtime ../website-investigator-runtime-private
   ```

   Lim inn tokenene når den skjulte ledeteksten spør. De lagres i macOS-nøkkelringen,
   ikke i prosjektfiler eller GitHub.

Oppsettet kontrollerer Slack-tilgangen, låser tjenesten til det installerte
arbeidsområdet og starter den automatisk i bakgrunnen ved innlogging.

## Bruk

Skriv i Slack:

```text
/undersok nettadresse.no
```

Slack viser en privat kvittering med én gang. Resultatet og HTML-rapporten kommer som
en direktemelding fra Website Investigator. Macen må være på og tilkoblet.

## Tilgang

Som standard kan medlemmer av det installerte Slack-arbeidsområdet bestille en
undersøkelse. Resultatene sendes alltid privat til bestilleren. Begrensning til bestemte
brukere eller kanaler kan legges i den private `config/slack.yml` med Slack-ID-er; slike
ID-er skal aldri legges i det offentlige repoet.

## Lokal kontroll

Denne kontrollen sender ingen Slack-melding:

```bash
wi slack doctor --runtime ../website-investigator-runtime-private
```
