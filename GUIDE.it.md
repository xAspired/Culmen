<img src="docs/images/icon-512.png" alt="Culmen" width="96" align="right">

# Culmen, spiegato da zero

*Versione italiana di [`GUIDE.md`](GUIDE.md). / Italian version of
[`GUIDE.md`](GUIDE.md).*

Questa guida non dà per scontato **nulla** — né meccanica orbitale, né
radiotecnica, né operazioni satellitari. Se sai già cosa sono EIRP e G/T,
quello che cerchi è [`docs/math/`](docs/math/); questo file è l'altra porta.

Tutto è spiegato nell'ordine in cui il software stesso calcola, così alla fine
non saprai solo cosa significano le parole: saprai quale parte di Culmen
produce ogni numero e dove guardare quando uno di quei numeri ti sembra
sbagliato.

**Indice**

1. [Il problema in una pagina](#1-il-problema-in-una-pagina)
2. [Dov'è il satellite? — orbite e TLE](#2-dovè-il-satellite--orbite-e-tle)
3. [Riesco a vederlo? — passaggi, azimut, elevazione](#3-riesco-a-vederlo--passaggi-azimut-elevazione)
4. [Il collegamento radio funziona? — il link budget](#4-il-collegamento-radio-funziona--il-link-budget)
5. [Quanti dati ci stanno? — volume dati](#5-quanti-dati-ci-stanno--volume-dati)
6. [Quale contatto è il migliore? — validazione e scheduling](#6-quale-contatto-è-il-migliore--validazione-e-scheduling)
7. [Il glossario](#7-il-glossario)
8. [Perché ogni numero si porta dietro le sue carte](#8-perché-ogni-numero-si-porta-dietro-le-sue-carte)
9. [Cosa Culmen deliberatamente non è](#9-cosa-culmen-deliberatamente-non-è)

---

## 1. Il problema in una pagina

Un satellite in orbita bassa gira intorno alla Terra all'incirca ogni 90
minuti. La tua stazione di terra — una parabola, o un'antenna imbullonata su un
tetto — sta ferma in un punto. Il satellite è *raggiungibile* solo quando si
trova sopra il tuo orizzonte locale, il che succede qualche volta al giorno,
per una decina di minuti alla volta.

Quando è lassù, quattro cose distinte devono essere vere prima che tu ottenga
davvero i tuoi dati:

1. **Geometria.** Il satellite deve stare sopra l'orizzonte, e abbastanza in
   alto che palazzi, colline e i limiti meccanici dell'antenna stessa non lo
   blocchino.
2. **Fisica radio.** Il segnale deve arrivare abbastanza forte, *rispetto al
   rumore*, perché il ricevitore lo decodifichi. La visibilità non lo
   garantisce affatto: un sacco di passaggi perfettamente visibili sono
   radio-impossibili.
3. **Tempo.** Il collegamento deve reggere abbastanza a lungo da spostare i
   dati che hai.
4. **Risorse.** Hai un'antenna e magari diversi satelliti, che la vogliono
   tutti in orari sovrapposti.

Culmen risponde a tutte e quattro e — questa è la sua vera ragione di esistere
— quando la risposta è *no*, ti dice **quale delle quattro è fallita, di
quanto, e cosa la sistemerebbe**. Un sacco di software ti disegna un
passaggio. Pochissimo ti dice che a quel passaggio mancavano 4.2 dB di margine
e che una parabola da 4.5 m invece che da 3 m lo chiuderebbe.

**Una definizione prima di tutto il resto**, perché metà di questa guida ci si
appoggia:

> **dB (decibel).** Un modo di scrivere i rapporti che trasforma le
> moltiplicazioni in addizioni. +3 dB vuol dire "circa il doppio". +10 dB vuol
> dire "dieci volte tanto". +20 dB è cento volte, +30 dB mille. Il segno meno
> è una divisione: −3 dB è la metà.
>
> Gli ingegneri radio lo usano perché fra il trasmettitore e il ricevitore un
> segnale viene moltiplicato e diviso da una dozzina di fattori — potenza,
> concentrazione dell'antenna, distanza, pioggia — e i numeri in gioco coprono
> venti ordini di grandezza. In decibel tutta la catena diventa una colonna di
> numeri da sommare. Quella colonna è il *link budget*, ed è letteralmente il
> motivo per cui si usa la parola "budget": sembra contabilità, perché lo è.

---

## 2. Dov'è il satellite? — orbite e TLE

### 2.1 L'ingresso: un TLE

Le posizioni dei satelliti vengono pubblicate come **TLE** — *Two-Line Element
set*, insieme di elementi su due righe. È esattamente quel che dice il nome:
due righe da 69 caratteri, un formato a larghezza fissa degli anni Sessanta che
è ancora la valuta universale dei dati orbitali. Uno vero fa così:

```
ISS (ZARYA)
1 25544U 98067A   24015.50000000  .00016717  00000-0  30474-3 0  9993
2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.49309239432299
```

Ogni campo significa qualcosa (inclinazione, eccentricità, moto medio,
resistenza atmosferica), ma non ti serve leggerlo a mano. Quello che ti serve
sapere sono le tre cose che fregano la gente:

- **Un TLE è un'istantanea, e scade.** Descrive l'orbita in un istante — la sua
  *epoca* — e più lontano predici da quell'istante, peggiore è la risposta.
  Culmen avverte sopra i **7 giorni** di età e rifiuta sopra i **30**. Nel
  lancio d'esempio qui sotto vedrai `TLE age at AOS: +0.08 days`: quello è un
  TLE in salute.
- **Un TLE funziona solo con la matematica giusta.** Non è una lista di
  coordinate: è un insieme di parametri per un algoritmo specifico, **SGP4**.
  Dallo a qualcos'altro e ottieni numeri che sembrano a posto e sono sbagliati.
- **I TLE vengono da qualche parte, con delle regole attaccate.** Culmen li
  scarica da [CelesTrak](https://celestrak.org/) con
  `scripts/fetch_tle.py`, che impone un intervallo minimo di 3 ore fra un
  download e l'altro e si identifica — perché un servizio pubblico che è
  costretto a limitarti è un servizio pubblico di cui stai abusando. I file
  scaricati **non** finiscono nel repository; vedi
  [`data/README.md`](data/README.md).

### 2.2 Il propagatore: SGP4

**SGP4** (*Simplified General Perturbations, model 4*) è l'algoritmo che
trasforma un TLE più un istante in una posizione e una velocità. Tiene conto
del fatto che la Terra non è un punto materiale — è schiacciata, e il rigonfio
equatoriale fa ruotare lentamente l'orbita — e della resistenza atmosferica.

Culmen non lo reimplementa. Usa la libreria standard `sgp4` e la verifica
contro i **vettori di verifica ufficiali di Vallado**, il caso di test di
riferimento che pubblicano i manutentori dell'algoritmo stesso. Culmen è
d'accordo con loro entro **2 × 10⁻⁷ km** — 0.2 millimetri. Non è un numero di
cui vantarsi: è il numero che dimostra che i collegamenti sono giusti, perché
sbagliare un sistema di riferimento o una scala di tempo produce errori di
*chilometri*, non di millimetri.

### 2.3 La trappola che frega tutti: i sistemi di riferimento

Questa è la singola fonte più comune di risposte silenziosamente sbagliate in
questo campo, quindi si merita un paragrafo suo.

Una posizione non significa niente se non dici *rispetto a cosa* è misurata.
I sistemi in gioco sono tre:

| Sistema | Fisso rispetto a | Serve per |
|---|---|---|
| **TEME** | le stelle (più o meno) | quello che SGP4 restituisce |
| **ITRF / ECEF** | la Terra che ruota | dov'è la tua stazione di terra |
| **Geodetico** | — | latitudine, longitudine, quota |

**SGP4 ti dà TEME.** TEME sta per *True Equator, Mean Equinox* — un sistema
quasi-inerziale che **non** ruota con la Terra. La tua stazione è a Padova, e
Padova **ruota** con la Terra, a circa 465 m/s all'equatore. Sottrai una
posizione dall'altra senza convertire e il satellite risulta nel posto
sbagliato di centinaia di chilometri, in un modo abbastanza plausibile da
finire in produzione.

Peggio ancora, TEME **non** è nemmeno J2000 — l'altro sistema inerziale comune
— pur essendogli quasi identico. La differenza è abbastanza piccola da passare
un controllo superficiale e abbastanza grande da rovinare una previsione.

Culmen converte TEME → ITRF esplicitamente, usando l'angolo di rotazione
terrestre e il moto polare, e
[`docs/math/sgp4-and-teme.md`](docs/math/sgp4-and-teme.md) scrive per esteso la
conversione. **Se da questa guida ti porti via una cosa sola, portati via
questa.**

### 2.4 L'altra trappola: cosa vuol dire "latitudine"

Di latitudini ce ne sono due, e non sono lo stesso numero.

- La **latitudine geocentrica** è l'angolo dall'equatore a una linea tirata
  fino al centro della Terra.
- La **latitudine geodetica** — quella di ogni mappa, di ogni GPS e di ogni
  scheda tecnica di stazione — è l'angolo dall'equatore alla *verticale
  locale*, la direzione in cui pende un filo a piombo.

Differiscono perché la Terra è un ellissoide, schiacciato di circa una parte su
298. Alle medie latitudini lo scarto arriva a **0.19°**, che a terra fa circa
**21 km**. Punta un'antenna con quella sbagliata e un fascio stretto manca il
bersaglio completamente. Culmen usa **WGS84 geodetico** dappertutto — lo
standard del GPS — e converte con il metodo di Bowring
([`docs/math/geodetic.md`](docs/math/geodetic.md)).

### 2.5 E nemmeno il tempo è semplice

Tre complicazioni, tutte gestite da Culmen e tutte da conoscere:

- **UTC è discontinuo.** Ogni tanto ci infilano un *secondo intercalare* per
  restare al passo con la rotazione terrestre, che è leggermente irregolare.
  Sottrarre due timestamp UTC a cavallo di uno di questi dà una risposta
  sbagliata di un secondo. Internamente Culmen lavora su scale di tempo
  continue e presenta UTC solo in uscita.
- **La precisione dei numeri in virgola mobile finisce.** Una Data Giuliana
  oggi vale circa 2 460 000. Un float a 64 bit a quella grandezza risolve circa
  **40 microsecondi** — e il satellite in quel tempo si sposta di 30 cm. Culmen
  porta le date come **due numeri** (giorni interi + frazione): è prassi
  standard, e non è opzionale.
- **I timestamp senza fuso orario vengono rifiutati.** Un datetime senza
  timezone è un'ambiguità che aspetta di diventare un bug, quindi Culmen
  solleva un errore invece di tirare a indovinare UTC.

---

## 3. Riesco a vederlo? — passaggi, azimut, elevazione

### 3.1 Il vocabolario

Un **passaggio** (*pass*) è un periodo continuo durante il quale il satellite
sta sopra l'orizzonte della tua stazione. Si descrive con:

| Termine | Significato |
|---|---|
| **AOS** | *Acquisition of Signal* — il passaggio comincia |
| **LOS** | *Loss of Signal* — il passaggio finisce |
| **Azimut** | direzione bussola verso il satellite: 0° = Nord, 90° = Est, 180° = Sud, 270° = Ovest |
| **Elevazione** | angolo sopra l'orizzonte: 0° = sull'orizzonte, 90° = allo zenit |
| **Culminazione** | l'istante di elevazione massima — il punto più alto del passaggio |
| **Range** | distanza in linea retta dal satellite, in km |
| **Range rate** | quanto velocemente quella distanza cambia; negativo = si avvicina |

> Il progetto prende il nome dalla **culminazione** — il punto più alto di un
> passaggio, il momento in cui tutto è al meglio. `Culmen` è la parola latina.

Azimut ed elevazione insieme sono i **look angles**: esattamente i due numeri
che imposteresti su un rotore per puntare la cosa. Calcolarli vuol dire
convertire la posizione del satellite (solidale alla Terra) in un sistema
locale **ENU** (East-North-Up) centrato sulla tua stazione — la riduzione
topocentrica di [`docs/math/topocentric.md`](docs/math/topocentric.md).

### 3.2 Un passaggio vero, dai dati d'esempio inclusi

Questo è output autentico di `python examples/01_passes.py`, per la ISS su
Padova:

```
Padova: 3 pass(es) for NORAD 28057

Highest pass: 2006-06-26 20:40:09Z -> 20:50:25Z, 10.3 min, peak 82.8 deg
TLE age at AOS: +0.08 days

  time        az      el    range_km   range_rate_km_s
  20:40:09   161.3   10.0     2316.6     -6.627
  20:42:01   160.1   23.1     1593.9     -6.177
  20:43:53   155.3   49.9      982.2     -4.280
  20:44:49   138.5   73.8      808.2     -1.680
  20:45:45     8.6   72.7      812.8     +1.837
  20:47:37   350.1   33.3     1277.4     +5.609
  20:50:25   347.8   10.0     2333.0     +6.623
```

Leggilo e la fisica viene fuori da sola:

- Il satellite **sorge a sud-sudest** (az 161°) e **tramonta a nord-nordovest**
  (az 348°). Un passaggio, una spazzata attraverso il cielo.
- Il **range varia di quasi un fattore tre** — 2317 km all'orizzonte, 808 km
  allo zenit. Tienilo a mente: il paragrafo 4 parla praticamente solo di quanto
  questo ti costa.
- Il **range rate cambia segno alla culminazione**, da −6.6 km/s (si avvicina)
  a +6.6 km/s (si allontana). Quel cambio di segno *è* la culminazione, ed è
  proprio quello che il cercatore di passaggi risolve.
- L'**azimut ruota di 130° in meno di due minuti** intorno al picco. Un
  passaggio alto sembra ideale ed è meccanicamente brutale: è lì che i rotori
  perdono l'inseguimento.
- Il passaggio comincia e finisce esattamente a **10.0°** perché quella è
  l'elevazione minima configurata per Padova, non perché il satellite sia
  comparso lì.

### 3.3 Come Culmen trova i passaggi (e il bug che ci ha insegnato a testarlo)

Trovare AOS e LOS vuol dire trovare dove l'elevazione attraversa la tua soglia;
trovare la culminazione vuol dire trovare dove la sua derivata è zero. Culmen
campiona grossolanamente, poi raffina con un cercatore di radici (Brent) per
gli attraversamenti e con una ricerca limitata per il picco.

Qui c'è una trappola vera, e questo progetto ci è cascato. I risolutori
numerici usano tolleranze in parte *relative* alla grandezza dell'ingresso.
Dagli una Data Giuliana da 2 460 000 e la tolleranza relativa diventa circa
**0.04 giorni — un'ora**, che è più lunga dell'intero passaggio. Il risolutore
tornava dopo **una sola iterazione**, dichiarava **successo**, e dava
elevazioni di picco fino a **17° più basse** del vero.

La correzione: raffinare in **secondi relativi all'inizio della finestra**, mai
in date assolute. Il test che l'ha beccato —
`test_reported_maximum_is_the_real_maximum` — calcola il massimo vero per forza
bruta e confronta. Sta nella suite in pianta stabile.

È il sapore di tutto il progetto: i bug pericolosi non sono i crash, sono i
numeri plausibili e sbagliati.

### 3.4 L'orizzonte non è piatto

Le stazioni vere hanno alberi, palazzi e colline. Culmen supporta un **profilo
di orizzonte**: un'elevazione minima per settore di azimut, così puoi dire "10°
dappertutto, tranne 25° verso nordest dove c'è il palazzo". Un passaggio
geometricamente visibile ma bloccato da quel profilo viene riportato come
bloccato, non come utilizzabile.

Due semplificazioni sono dichiarate invece che nascoste: le elevazioni sono
**geometriche**, senza modello di rifrazione atmosferica (la rifrazione alza
gli oggetti vicino all'orizzonte di circa mezzo grado), e il profilo di
orizzonte è una funzione a gradini fra un settore e l'altro.

---

## 4. Il collegamento radio funziona? — il link budget

La geometria dice che il satellite è lassù. Questo paragrafo chiede se riesci
davvero a sentirlo. La risposta è un unico numero chiamato **margine**, e tutto
quello che segue è l'aritmetica che ci porta.

### 4.1 La catena, a parole

La potenza esce dal trasmettitore del satellite. La sua antenna la concentra
nella tua direzione. Si sparpaglia lungo la distanza. Un po' viene assorbita
dall'atmosfera e, se piove, parecchia di più. La tua antenna ne raccoglie una
parte. Il tuo ricevitore ci aggiunge del rumore suo. Quel che conta alla fine
non è quanto segnale è arrivato: è **quanto segnale è arrivato rispetto al
rumore**.

### 4.2 Termine per termine

**EIRP — Effective Isotropic Radiated Power**, in dBW.

> Quanto è forte la trasmissione *nella tua direzione*. È la potenza del
> trasmettitore più il guadagno dell'antenna, meno le perdite nei cavi.
>
> "Isotropo" vuol dire "che irradia ugualmente in tutte le direzioni" —
> l'antenna di riferimento immaginaria con cui si confronta tutto. L'EIRP
> risponde a: *quanto dovrebbe essere potente un radiatore isotropo nudo, per
> mettere questo tanto di segnale dove sto io?*
>
> `EIRP_dBW = potenza_trasmessa_dBW + guadagno_antenna_dBi − perdite_dB`

**Guadagno d'antenna**, in dBi.

> Un'antenna non crea potenza: la *concentra*, come il riflettore di una
> torcia. Il guadagno è quanto più segnale ottieni nella direzione favorita
> rispetto a quello che darebbe un radiatore isotropo — da cui la "i" di
> **dBi**.
>
> Per una parabola dipende dall'area, dalla lunghezza d'onda e da un fattore di
> efficienza (tipicamente 0.5–0.7, perché nessuna parabola è illuminata
> perfettamente):
>
> `G_dBi = 10·log₁₀(η · (π·D/λ)²)`
>
> Una parabola da 3 m a 8.2 GHz con efficienza 60% dà **46.0 dBi** — circa
> 40 000× di concentrazione. Parabola più grande o frequenza più alta vuol dire
> più guadagno, e anche fascio più stretto: ecco perché le parabole grandi
> hanno bisogno di un puntamento buono.
>
> Attenzione ai **dBd**, un'unità più vecchia riferita a un dipolo invece che a
> un isotropo: `dBi = dBd + 2.15`. Confonderli ti regala 2.15 dB di margine
> immaginario.

**FSPL — Free-Space Path Loss** (perdita di percorso in spazio libero), in dB.

> Il termine grosso. Il segnale si distribuisce sulla superficie di una sfera
> che si espande, quindi la densità di potenza cala col quadrato della
> distanza. In unità pratiche:
>
> `FSPL_dB = 32.4478 + 20·log₁₀(distanza_km) + 20·log₁₀(frequenza_MHz)`
>
> Per il nostro passaggio ISS a 8.2 GHz: **178.0 dB all'orizzonte** (2317 km)
> contro **166.3 dB a 600 km**. Sono **12 dB di escursione** — un fattore 16 in
> potenza ricevuta — *dentro un singolo passaggio di dieci minuti*.
>
> È per questo che Culmen calcola il budget **lungo tutto il passaggio** invece
> che una volta sola. Un budget valutato solo alla culminazione ti dirà che
> funziona un collegamento che in realtà cade a entrambi gli estremi.

**Attenuazione atmosferica e da pioggia**, in dB.

> L'aria assorbe energia radio — soprattutto ossigeno e vapore acqueo — e la
> pioggia ne assorbe molta di più. Entrambe peggiorano a bassa elevazione,
> perché un percorso più radente passa più tempo dentro l'atmosfera.
>
> I due termini **non** sono della stessa taglia, e confonderli è un errore
> vero che questo progetto ha commesso e corretto. Per Padova a 8.2 GHz e 10°
> di elevazione:
>
> | | |
> |---|---|
> | Assorbimento gassoso (ITU-R P.676) | **0.26 dB** |
> | Pioggia (ITU-R P.618, 0.01% dell'anno) | **5.55 dB** |
>
> Il gas in banda X è un errore di arrotondamento. **È la pioggia che ti mangia
> il margine.** A 20 GHz la stessa pioggia costa circa **39 dB**, che è
> esattamente il motivo per cui i downlink in banda X esistono ancora.
>
> L'attenuazione da pioggia è una *statistica*, non un valore: "superamento
> 0.01%" vuol dire "questo o peggio, per lo 0.01% di un anno medio" — cioè
> disponibilità 99.99%. Il numero cambia di diversi dB fra 0.1% e 0.001%,
> quindi **un margine dichiarato senza il suo obiettivo di disponibilità non è
> un margine**. Culmen restituisce la percentuale insieme al valore, sempre.

**G/T — Gain over Temperature** (guadagno su temperatura), in dB/K.

> L'unica cifra di merito di una stazione ricevente: quanto concentra, diviso
> quanto rumore aggiunge. Due stazioni con la stessa parabola possono
> differire di 10 dB qui, se una ha un amplificatore freddo e silenzioso e
> l'altra no.
>
> `G/T = guadagno_antenna_dBi − 10·log₁₀(temperatura_rumore_sistema_K)`
>
> "Temperatura" non è il meteo. La potenza di rumore è proporzionale a una
> temperatura equivalente, quindi gli ingegneri quotano il rumore *come* una
> temperatura in kelvin — la somma di cielo, terreno che l'antenna vede in
> parte, amplificatore e cavi. Sale ripidamente a bassa elevazione, perché
> un'antenna puntata in basso vede terreno caldo. (Culmen al momento la tratta
> come costante e lo dichiara: assunzione A-RF-2.)

**C/N₀ — rapporto portante / densità di rumore**, in dB-Hz.

> Tutto quanto sopra, combinato in un numero solo:
>
> `C/N₀ = EIRP − FSPL − altre_perdite + G/T − k`
>
> dove `k` è la **costante di Boltzmann**, −228.6 dBW/(Hz·K), una costante di
> natura che converte una temperatura in una potenza di rumore. L'unità strana
> dB-Hz viene dal fatto che questo è un rapporto *per hertz di banda*.

**Eb/N₀ — energia per bit su densità di rumore**, in dB.

> C/N₀ descrive il canale. Eb/N₀ descrive se i tuoi *dati* ci sopravvivono, ed
> è il numero rispetto al quale i ricevitori sono effettivamente specificati:
>
> `Eb/N₀ = C/N₀ − 10·log₁₀(bitrate_bps)`
>
> Raddoppiare il bitrate costa esattamente 3 dB. È il compromesso fondamentale
> di tutto il campo: **velocità contro portata**.

**Margine**, in dB. La risposta.

> `Margine = Eb/N₀_ottenuto − Eb/N₀_richiesto`
>
> Positivo vuol dire che il collegamento chiude. Negativo vuol dire di no.
> Qualche dB di margine è prudente; zero è un testa o croce, perché ogni
> ingresso ha la sua incertezza.

### 4.3 Il tutto, con numeri veri

Un downlink in banda X da 20 W (13 dBW), antenna satellitare da 12 dBi,
25 Mbps, verso una parabola da 3 m con sistema a 150 K, che richiede 4 dB di
Eb/N₀. Questi sono output reali del codice di Culmen:

| | a 600 km (alto) | a 2000 km (basso) |
|---|---|---|
| FSPL | 166.29 dB | 176.74 dB |
| C/N₀ | 111.19 dB-Hz | 100.73 dB-Hz |
| Eb/N₀ | 37.21 dB | 26.75 dB |
| **Margine** | **+33.21 dB** | **+22.75 dB** |

Chiudono entrambi con comodità — e lo *stesso* collegamento sta 10.5 dB meglio
in cima al passaggio che ai bordi, solo per via della distanza. Adesso
sottraici i 5.8 dB di atmosfera del paragrafo 4.2 a quella bassa elevazione, e
un collegamento con margini più risicati comincia a fallire esattamente dove
sulla carta sembrava a posto.

### 4.4 Cosa è verificato contro cosa

Il link budget è verificato contro un **caso pubblicato in un workshop ITU-R**.
È d'accordo entro **0.2 dB**, e quei 0.2 dB sono un'incoerenza documentata
*nella fonte pubblicata* che questo progetto **non** ha coperto allargando la
tolleranza. Quella decisione sta in [`CONTRIBUTING.md`](CONTRIBUTING.md),
perché è lo stile della casa: una discrepanza che sai spiegare vale più di un
test verde che non sai spiegare.

---

## 5. Quanti dati ci stanno? — volume dati

Adesso la parte semplice, che è semplice solo perché le parti difficili sono
venute prima.

Sai quando il collegamento chiude e quando smette di chiudere. L'**intervallo
di chiusura** è la porzione di passaggio in cui il margine è positivo — che può
essere più corta del passaggio stesso, e quella differenza è tutto il punto.

```
secondi_utili = intervallo_di_chiusura − tempo_di_acquisizione − tempo_di_setup
bit           = secondi_utili × bitrate × efficienza_di_framing
```

- **Tempo di acquisizione**: al ricevitore serve un momento per agganciare la
  portante e sincronizzarsi sui bit. Non è gratis.
- **Efficienza di framing**: non ogni bit trasmesso è tuo. L'incapsulamento di
  protocollo, i codici di correzione d'errore e i marcatori di
  sincronizzazione consumano capacità. Una frame CCSDS con codifica
  Reed-Solomon consegna magari il ~92% di payload. Culmen ti obbliga a
  dichiararlo invece di assumere il 100%.

Per il passaggio ISS vero di prima — 618 secondi, meno 20 s di acquisizione e
10 s di setup, a 25 Mbps con framing al 92%:

```
588 s × 25 000 000 bit/s × 0.92 = 13.52 Gbit = 1.69 GB
```

Attenzione: **GB = 10⁹ byte**, decimali, come si usa in tutte le
telecomunicazioni — non 2³⁰. Confondere i due è un errore del 7%, che è
esattamente la dimensione dell'effetto che la gente va a cercare quando un
downlink "rende meno del previsto".

Culmen inverte anche il calcolo: dato un volume da spostare, quanti secondi di
contatto ti servono? È questo che trasforma "il passaggio dura 10 minuti" in
"ti servono tre passaggi".

**Nota di onestà:** a differenza di SGP4 e del link budget, per il volume dati
non esiste un caso di riferimento esterno contro cui verificare — dipende
interamente da uno specifico sistema di terra. Il modulo di test lo dichiara
nel proprio docstring e fissa invece proprietà matematiche e coerenza inversa.
Dove Culmen non può verificarsi contro il mondo, lo dice.

---

## 6. Quale contatto è il migliore? — validazione e scheduling

### 6.1 Il Contact Validator

È il componente per cui l'intero progetto esiste. Prende un contatto candidato
ed esegue ogni controllo in modo indipendente; ognuno restituisce **PASS**,
**FAIL**, **WARN** o **SKIPPED** — con il valore atteso, il valore effettivo e
lo scarto:

- l'elevazione di picco è sopra il minimo di missione?
- il contatto è abbastanza lungo?
- il collegamento chiude, con abbastanza margine?
- l'antenna riesce meccanicamente a inseguirlo (velocità di brandeggio,
  keyhole, finecorsa)?
- il volume dati richiesto ci sta davvero?
- il TLE è abbastanza fresco da fidarsi di questa previsione?

I controlli si combinano in un verdetto — **VALID**, **CONDITIONALLY_VALID** o
**INVALID** — e, cosa cruciale, in **suggerimenti derivati dal controllo che è
fallito**. Non consigli generici: se il controllo sul margine è fallito per
4.2 dB, il suggerimento è calcolato da quei 4.2 dB.

**SKIPPED** merita enfasi. Se non hai fornito i limiti di brandeggio
dell'antenna, il controllo relativo non passa in silenzio: riporta che non ha
potuto essere eseguito. Un verdetto che sembra validato ma ha saltato in
sordina metà dei suoi controlli è esattamente il modo di fallire che questo
progetto è costruito per prevenire.

### 6.2 Lo scheduler

Hai diversi satelliti, una o due antenne, e passaggi sovrapposti. Assegnarli in
modo ottimo è un problema NP-difficile in generale, quindi Culmen usa un
algoritmo **greedy**: ordina i candidati, prendi il migliore che ci sta ancora,
ripeti.

Due proprietà contano più dell'ottimalità:

- **È deterministico.** L'ordinamento usa un ordine totale con spareggio
  sull'identità, quindi gli stessi ingressi producono sempre lo stesso piano.
  Un pianificatore che rimescola fra un lancio e l'altro è inutilizzabile,
  quanto buone siano le sue risposte.
- **È onesto sul fatto di essere subottimale.** L'assunzione A-SCHED-1 lo dice,
  e un test *dimostra un caso in cui il greedy viene battuto*. Culmen
  distribuisce un esempio della propria debolezza, scritto apposta.

Lo scheduler prenota come risorsa sia l'antenna **sia** il satellite. Sembra
ovvio; era un bug vero, trovato lanciando `examples/03_schedule.py` e notando
un satellite prenotato su due antenne nello stesso istante, con i suoi dati
contati due volte.

---

## 7. Il glossario

| Termine | Per esteso | In una riga |
|---|---|---|
| **AOS / LOS** | Acquisition / Loss of Signal | Inizio e fine di un passaggio |
| **Azimut** | — | Direzione bussola verso il satellite (0° = Nord) |
| **C/N₀** | Carrier to Noise-density | Qualità di segnale del canale, dB-Hz |
| **CCSDS** | Consultative Committee for Space Data Systems | L'ente che standardizza i protocolli dati spaziali |
| **dB** | Decibel | Rapporti come addizioni; +3 dB ≈ doppio, +10 dB = ×10 |
| **dBi / dBd** | — | Guadagno d'antenna vs isotropo / vs dipolo; `dBi = dBd + 2.15` |
| **dBW / dBm** | — | Potenza rispetto a 1 watt / a 1 milliwatt |
| **Eb/N₀** | Energia per bit / densità di rumore | Se i tuoi *dati* sopravvivono; l'unità in cui si specificano i ricevitori |
| **ECEF / ITRF** | Earth-Centred Earth-Fixed | Sistema che ruota con la Terra |
| **EIRP** | Effective Isotropic Radiated Power | Quanto è forte la trasmissione nella tua direzione |
| **Elevazione** | — | Angolo sopra l'orizzonte; 90° = allo zenit |
| **ENU** | East-North-Up | Sistema locale centrato sulla tua stazione |
| **FSPL** | Free-Space Path Loss | Perdita dovuta alla sola distanza; il termine dominante |
| **Latitudine geodetica** | — | La latitudine di mappe e GPS, dalla verticale locale |
| **G/T** | Gain over Temperature | Cifra di merito di una stazione ricevente, dB/K |
| **ITU-R** | International Telecommunication Union, settore Radiocomunicazioni | Pubblica i modelli di propagazione (P.676, P.618, P.372) |
| **Keyhole** | — | Il cono cieco allo zenit dove una montatura az/el non riesce a brandeggiare abbastanza in fretta |
| **LEO** | Low Earth Orbit | ~200–2000 km; ~90 min per orbita |
| **NORAD ID** | — | Il numero di catalogo a cinque cifre di un oggetto |
| **Passaggio** | *pass* | Un periodo continuo sopra l'orizzonte |
| **Range rate** | — | Velocità di variazione della distanza; genera lo spostamento Doppler |
| **SGP4** | Simplified General Perturbations 4 | L'algoritmo per cui un TLE è fatto |
| **TEME** | True Equator, Mean Equinox | Il sistema in uscita da SGP4 — né J2000 né solidale alla Terra |
| **TLE** | Two-Line Element set | Il formato anni '60 in cui si pubblicano le orbite |
| **UTC / TAI / TT / UT1** | — | Scale di tempo; solo UTC ha i secondi intercalari |
| **WGS84** | World Geodetic System 1984 | L'ellissoide usato dal GPS; il riferimento di Culmen |
| **Banda X / Banda Ka** | — | ~8 GHz / ~20–30 GHz; la Ka è più veloce e molto più sensibile alla pioggia |

---

## 8. Perché ogni numero si porta dietro le sue carte

Ogni grandezza calcolata in Culmen è un oggetto `Computed` che porta con sé,
insieme al valore: la sua **unità**, un **riferimento** alla formula
documentata, gli **ingressi** da cui è derivata e le **assunzioni** su cui
poggia.

Non è burocrazia. Se uno strumento ti dice che un contatto funzionerà e poi non
funziona, l'unica domanda utile è *quale passaggio era sbagliato* — e da un
numero nudo non puoi rispondere. Ogni risposta dell'API porta questa traccia,
ed è per questo che le segnalazioni di bug di questo progetto possono
semplicemente incollarla.

Dallo stesso istinto discendono tre regole di casa, imposte da test che fanno
fallire la build:

- **Le unità vivono nei nomi.** `range_km`, `freq_hz`, `power_dbw`. Un test
  analizza ogni struttura dati e rifiuta un campo numerico senza suffisso di
  unità. Ha già beccato più di una volta i nomi scelti dall'autore.
- **Ogni riferimento a una formula deve risolvere.** Un test controlla che ogni
  citazione punti a un documento che esiste. Una traccia di audit che cita una
  nota mancante è peggio di nessuna traccia.
- **Ogni semplificazione è numerata e dichiarata.**
  [`docs/math/assumptions.md`](docs/math/assumptions.md) le elenca tutte —
  A-GEO-3 per la rifrazione, A-RF-2 per la temperatura di rumore, A-SCHED-1 per
  lo scheduling greedy. Le voci non si cancellano mai, si emendano soltanto con
  la fase che le ha rimosse, così la storia di ciò che una volta era sbagliato
  resta leggibile.

E una regola sopra tutte, da [`CONTRIBUTING.md`](CONTRIBUTING.md):

> **Un numero senza un riferimento esterno non è verificato**, e **non
> inventare mai un numero per far funzionare qualcosa.** Un default plausibile
> per una perdita atmosferica, una coordinata di stazione presa a memoria, una
> tolleranza allargata finché non diventa verde — ognuna di queste è peggio di
> una lacuna evidente, perché è invisibile.

---

## 9. Cosa Culmen deliberatamente non è

- **Non è un tracker satellitare.** Non fa il "dov'è adesso" in tempo reale:
  risponde a domande di pianificazione sul futuro.
- **Non è controllo di antenne o radio.** Calcola; non punta niente e non manda
  in trasmissione niente. È uno strumento di **analisi**.
- **Non è un trasmettitore, e non è una licenza.** Il fatto che una frequenza
  sia pubblicamente documentata non è *mai* un'autorizzazione a trasmetterci
  sopra. Le licenze sono una faccenda legale fra te e il tuo regolatore
  nazionale, e niente di quello che produce questo software la cambia.
- **Niente IA, da nessuna parte nel prodotto.** Nessun modello, nessuna
  inferenza, nessuna euristica appresa. Ogni uscita è una funzione
  deterministica dei suoi ingressi: gli stessi ingressi e la stessa versione
  del motore producono gli stessi numeri, per sempre. È
  [ADR 0007](docs/adr/0007-no-ai-in-the-product.md), e per uno strumento il cui
  mestiere è un verdetto tracciabile non è una limitazione: è il requisito.
- **Non scarica niente per conto tuo.** L'API non scarica mai dati di catalogo
  in silenzio. Rispettare i limiti di frequenza, la licenza e l'attribuzione di
  un fornitore di dati è responsabilità dell'operatore, e nascondergliela
  sarebbe un pessimo favore.

---

## Dove andare adesso

| Se vuoi | Leggi |
|---|---|
| Farlo partire | [`README.md`](README.md) — un comando solo |
| La matematica vera, con le fonti | [`docs/math/`](docs/math/) |
| Perché il progetto ha questa forma | [`docs/adr/`](docs/adr/) — dieci decisioni, con le alternative scartate |
| Ogni semplificazione dichiarata | [`docs/math/assumptions.md`](docs/math/assumptions.md) |
| Aggiungere la tua stazione o altri satelliti | [`data/README.md`](data/README.md) |
| Contribuire | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
