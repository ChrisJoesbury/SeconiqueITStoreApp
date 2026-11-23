# Seconique IT Store

![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![Django](https://img.shields.io/badge/Django-6.1.3-green)
![Database](https://img.shields.io/badge/Database-SQLite-lightgrey)
![Status](https://img.shields.io/badge/Status-Active-success)

Seconique IT Store is a stockroom web application for **recording, issuing, and reporting IT assets and consumables**. Staff receive goods into shared bin locations, issue them to named people, and see what is held, where it sits, and when it needs reordering.

---

## 🚀 Overview

The application is a **Django web app** backed by a single SQLite database. Every signed-in user works with the same store data. Access depends on role: administrators manage the reference data and user accounts, standard users run the store, reporting users read the reports, and assignees exist only as names on an issue.

Key capabilities include:
- One barcode per physical asset, and quantity records for consumables
- Goods in, goods out, and stocktake, each written to a usage log
- Shared categories, bin locations, and comma-separated attributes
- Store contents, attribute catalogue, and analytics
- Barcode labels for assets and consumables

---

## 🛠️ Technologies Used

### Languages
- Python 3.12+

### Frameworks
- Django 6.1.3

### Barcodes
- python-barcode — Code 128 labels as inline SVG

### Database
- SQLite (`db.sqlite3` is included in the repository)

### Tested on
- **Python** 3.14
- **Django** 6.1.3
- **SQLite** (application data and the test suite)

---

## ✨ Features

- **Asset records** — receive, edit, issue, return, and delete one physical item per barcode
- **Consumable records** — receive, count, issue, and delete stock held as a quantity
- **Bin locations** — Disposal cage, Goods In, Goods Out, Main Store, and Server Room, with admin create, rename, and delete
- **Attributes** — comma-separated tags on assets and consumables, with a catalogue report
- **Holding limits** — reorder level and maximum quantity to hold, shown in analytics
- **Role separation** — administrators can change users, categories, and bin locations; other roles cannot

---

## 👥 Roles

| Role | Signs in | Can do |
| --- | --- | --- |
| Admin | Yes | Operational work, plus users, categories, bin locations, and analytics |
| Standard | Yes | Receive, issue, stocktake, and day-to-day stock records |
| Reporting | Yes | Analytics, store contents, attributes, and the usage log |
| Assignee | No | Named only when equipment is issued |

---

## 🧰 Installation

### 1. Clone the repository
```bash
git clone https://github.com/ChrisJoesbury/SeconiqueITStore.git
cd SeconiqueITStore
```

### 2. Create and activate a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
.venv\Scripts\activate             # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Apply migrations
`db.sqlite3` is already in the project. `migrate` brings that database up to date rather than starting from an empty store.

```bash
python manage.py migrate
```

### 5. Run the development server
```bash
python manage.py runserver
```

### 6. Open the store
- Store: http://127.0.0.1:8000/

`config/settings.py` uses the generated development secret key, with `DEBUG` turned on. That is suitable for local marking. Replace the key and turn debug off before any public deployment.

---

## 🔑 Sample accounts

The included database has one account for each role: `store.admin`, `store.standard`, `store.report`, and `joe.bloggs`.

Reset a forgotten password with:

```bash
python manage.py changepassword store.admin
```

---

## 🧪 Running Tests

The test suite lives in **`stockroom/tests.py`**. It covers stock movements, role access, barcode labels, maximum holding quantities, goods-in and goods-out search, the store contents report, attributes, and bin locations. Tests use Django's built-in test runner and build their own database. They do not change `db.sqlite3`.

From the repository root, with the virtual environment activated:

**macOS / Linux:**
```bash
python manage.py test stockroom.tests
```

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\python.exe manage.py test stockroom.tests
```

For verbose output (each test name as it runs), add `--verbosity=2`.

The suite contains **25 tests** in eight classes:

| Class | Covers | Tests |
| --- | --- | --- |
| `StockMovementTests` | Receipt, issue, stocktake, and date checks | 3 |
| `RoleAccessTests` | Sign-in and what each role is allowed to open | 8 |
| `ReceiptLabelTests` | Barcode labels before a record is saved | 3 |
| `MaxHoldTests` | Maximum quantity to hold and suggested orders | 4 |
| `MovementSearchTests` | Issuing and receiving from a name search | 2 |
| `StoreContentsReportTests` | The combined asset and consumable store list | 2 |
| `AttributeReportTests` | Cleaning and reporting comma-separated attributes | 1 |
| `BinLocationTests` | Seeded bins and admin create, rename, and delete | 2 |

GitHub Actions runs the same command on every push and pull request. The workflow is `.github/workflows/tests.yml`. It checks out the repository on Ubuntu, installs Python 3.14 and `requirements.txt`, then runs the Django test suite.

---

## 📁 Folder Structure

```
SeconiqueITStore/
├── requirements.txt          # Python dependencies
├── README.md                 # Project documentation
├── manage.py                 # Django command line
├── db.sqlite3                # Sample store database
├── .github/workflows/        # GitHub Actions test run
├── config/                   # Project settings, URLs, and WSGI
└── stockroom/                # Store application
    ├── models.py             # Assets, consumables, bins, usage
    ├── forms.py              # Validation and role-aware forms
    ├── views/                # Dashboard, stock, reports, users
    ├── templates/            # HTML templates
    ├── static/               # CSS, JavaScript, and logos
    ├── migrations/           # Database migrations
    └── tests.py              # Automated test suite
```

`.gitignore` excludes the virtual environment, bytecode, logs, local editor files, and environment files such as `.env`. `db.sqlite3` stays in the repository so the sample store is available with the code and the tests.

---

## 📬 Contact

**Chris Joesbury**
Wolverhampton, West Midlands
Email: chrisjoesbury@gmail.com
