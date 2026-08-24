# Slack-oppsett

Slack er brukerflaten. En godkjent bruker skriver `/undersok nettadresse.no` og får
resultatet og HTML-rapporten som en privat melding. Macen trenger ikke stå på.

## Slik flyter et oppdrag

1. Cloudflare kontrollerer at kommandoen virkelig kommer fra Slack.
2. Nettadressen krypteres før GitHub kontaktes.
3. Den offentlige GitHub-jobben ser bare kryptert tekst og en tilfeldig referanse.
4. Nettadressen, kildedataene og rapporten skrives bare til det private runtime-repoet.
5. Slack-boten sender resultatet bare til brukeren som bestilte undersøkelsen.

Cloudflare-mottakeren er stateless: den har ingen database og lagrer ingen mål eller
rapporter. Detaljert Worker-logging er deaktivert.

## Tilganger

Cloudflare har bare:

- Slacks signeringshemmelighet, som brukes til å kontrollere avsenderen.
- En GitHub-nøkkel avgrenset til å starte Actions i dette ene offentlige repoet.
- En krypteringsnøkkel og private Slack-ID-er for arbeidsområdet og tillatte brukere.

GitHub har bare:

- Bot-tokenet som kan sende private meldinger og filer i Slack.
- Den samme krypteringsnøkkelen.
- Den eksisterende, avgrensede deploy-nøkkelen til det private runtime-repoet.

Ingen hemmelige verdier skal ligge i filer, Git-historikk, Actions-inndata eller logger.

## Én gangs oppsett

1. Opprett Slack-appen fra `slack-app-manifest.yml`, etter at manifestets eksempeladresse
   er erstattet med den publiserte Cloudflare-adressen.
2. Installer appen i det private arbeidsområdet.
3. Lag en avgrenset GitHub-nøkkel som bare kan starte Actions i det offentlige repoet.
4. Legg Slacks signeringshemmelighet, GitHub-nøkkelen, krypteringsnøkkelen og de tillatte
   Slack-ID-ene inn som krypterte Cloudflare-secrets.
5. Legg Slack bot-tokenet og krypteringsnøkkelen inn som GitHub Actions-secrets.
6. Kjør en ekte undersøkelse og bekreft både privat Slack-levering, privat arkivering og
   at offentlig jobbvisning ikke inneholder nettadressen.

## Bruk

```text
/undersok nettadresse.no
```

Kvitteringen vises privat med én gang. Resultatet og den fullstendige HTML-rapporten
kommer som en direktemelding fra Website Investigator.

Rapporten begynner med en norsk journalistisk oppsummering. Den forklarer funn,
sikkerhetsnivå og viktige forbehold, og viser annonserklæringer, sikkerhetskontakt og
organisasjonsopplysninger når nettstedet publiserer dette. Tekniske rådata ligger i et
sammenleggbart vedlegg nederst.
