# Simulator de Consens Blockchain cu Replicare SQLite și Vizualizare Interactivă în Graf

Acest proiect reprezintă o aplicație blockchain demonstrativă dezvoltată în Python (Flask, SQLite) și HTML5 Canvas, concepută special ca proiect universitar pentru a vizualiza și înțelege procesele de consens peer-to-peer, propagarea blocurilor, crearea dinamica de portofele și influența latenței în rețea în timp real.

---

# 🔗 **[LINK REPOSITORY GITHUB: Aplicatie-Blockchain-Wallet](https://github.com/mihaicr3/Aplicatie-Blockchain-Wallet)**
# 🖥️ **[LINK INTERFAȚĂ LOCALĂ: http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 💡 Ce Face Aplicația (Funcționalități Principale)

1. **Consens de Tranzacționare (Regula 50% + 1)**:
   - Atunci când trimiteți o tranzacție standard între două portofele (de ex. de la Alice la Bob), nodul activ inițiază un sondaj de votare P2P.
   - Fiecare nod client online din rețea votează cu **YES** (dacă expeditorul are fonduri suficiente în baza de date locală SQLite) sau **NO** (dacă balanța este insuficientă).
   - Pentru a fi minată într-un bloc nou și salvată, tranzacția are nevoie de aprobarea a cel puțin **50% + 1** din noduri (adică minim 2 din cele 3 noduri ale simulării).

2. **Creare Dinamică de Portofele**:
   - Puteți înregistra utilizatori/portofele noi direct din panoul lateral (de ex. *Eve*).
   - Numele noului portofel este replicat instantaneu prin rute P2P către bazele de date SQLite ale tuturor nodurilor clienți.

3. **Generare de Monede (Minting)**:
   - Permite generarea/spawning-ul de monede noi direct dintr-un portofel special de sistem (`SYSTEM`) către orice utilizator, acțiune care simulează recompensa de minare și se aprobă automat.

4. **Sincronizare Automată pe Cel Mai Lung Lanț**:
   - Managerul de coordonare (`manager.py`) rulează un proces de fundal periodic (la fiecare 5 secunde) care interoghează înălțimea blockchain-ului pe toate nodurile active.
   - Dacă detectează un nod cu un lanț mai scurt sau deconectat anterior care a revenit online, îi trimite automat istoricul complet de blocuri și portofele pentru a se alinia la starea de adevăr majoritară.

5. **Graf Interactiv 2D Canvas (Înaltă Rezoluție)**:
   - Portofelele sunt randate ca noduri grafice poziționate automat în cerc, iar tranzacțiile ca săgeți cu etichete de sume.
   - **Navigare completă**: Puteți face drag-and-drop pe fundal pentru a translata (pan) graful, zoom cu rotița mouse-ului centrat pe poziția cursorului și butoane suprapuse pentru Zoom In (`➕`), Zoom Out (`➖`) și Reset View (`🏠`).
   - Click pe orice nod de portofel îl selectează pentru interacțiuni rapide (sold curent, emitere tranzacție, spawn).

6. **Control Latency (Simulare Întârzieri de Rețea)**:
   - Panoul lateral oferă slidere interactive pentru a stabili o latență asincronă între `0ms` și `2000ms` individual pentru fiecare client.
   - Astfel, puteți observa vizual modul în care nodurile returnează voturile în etape succesive în timpul procesului de consens.

---

## 🛠️ Ghid de Instalare și Configurare (Setup)

Urmați acești pași simpli pentru a rula aplicația local pe calculatorul dumneavoastră:

### 1. Cerințe de Sistem
Asigurați-vă că aveți instalat **Python 3** (recomandat Python 3.10 sau mai nou).

### 2. Instalare Dependențe
Deschideți un terminal în folderul proiectului și instalați bibliotecile necesare (Flask și Requests) prin `pip`:
```bash
pip install flask requests
```

### 3. Pornirea Simulatorului
Lansați scriptul principal de coordonare. Acesta va porni automat serverul interfeței web (portul 5000) și cele 3 noduri blockchain independente (porturile 5001, 5002 și 5003):
```bash
python manager.py
```

### 4. Accesarea Interfeței Web
După lansare, deschideți browserul de internet preferat și navigați la adresa:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 📂 Structura Proiectului
* `backend/blockchain.py`: Motorul blockchain, definirea claselor `Block`, `Transaction` și conexiunea SQLite pentru balanțe/portofele.
* `backend/node.py`: Serverul API Flask pentru un nod individual (consens, votare, tranzacții, replici).
* `manager.py`: Scriptul central care rulează rețeaua și bucla periodică de fundal pentru auto-sincronizarea nodurilor.
* `frontend/index.html`: Layout-ul interfeței grafice (glassmorphism UI).
* `frontend/style.css`: Fișierul de stilizare CSS (sistem de design premium cu umbre neon și fundal dinamic).
* `frontend/app.js`: Scriptul front-end care randeză Canvas-ul, capturează inputul mouse-ului pentru zoom/pan, efectuează polling-ul și controlează interacțiunea cu API-urile.