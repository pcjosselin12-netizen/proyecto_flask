from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import os
from fpdf import FPDF
from datetime import datetime

# ------------------- APP -------------------

app = Flask(__name__)
app.secret_key = "1234"

UPLOAD_FOLDER = 'uploads'
PDF_FOLDER = 'examenes'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)

# ------------------- BD SQLITE -------------------

db = sqlite3.connect("serviciomed.db", check_same_thread=False)
db.row_factory = sqlite3.Row

cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,
    password TEXT,
    carrera TEXT,
    expediente TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS encuesta_salud (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expediente TEXT,
    respuesta TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS examenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expediente TEXT,
    documento TEXT
)
""")

db.commit()

# ------------------- PREFIJOS -------------------

PREFIJOS = {
    "Ingeniería en Animación Digital y Efectos Visuales": "IADYEV",
    "Ingeniería en Sistemas Computacionales": "ISC",
    "Ingeniería Industrial": "II",
    "Ingeniería en Mecatrónica": "IM",
    "Ingeniería Química": "IQ",
    "Licenciatura en Gastronomía": "LG",
    "Licenciatura en Administración": "LA"
}

# ------------------- PDF -------------------

def generar_pdf_examen(formulario, expediente):
    pdf = FPDF()
    pdf.set_margins(12, 12, 12)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=12)

    ancho_util = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "EXAMEN MEDICO 2025-2", ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=9)

    for campo, valor in formulario.items():
        campo = campo.replace("_", " ").capitalize()
        texto = str(valor).replace("\n", " ").replace("\r", " ")
        linea = f"{campo}: {texto}"

        pdf.multi_cell(ancho_util, 5, linea)
        pdf.ln(1)

    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_pdf = f"examen_{expediente}_{fecha}.pdf"
    ruta = os.path.join(PDF_FOLDER, nombre_pdf)

    pdf.output(ruta)
    return nombre_pdf

# ------------------- LOGIN -------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nombre = request.form["nombre"]
        password = request.form["password"]

        cursor = db.cursor()
        cursor.execute(
            "SELECT * FROM usuarios WHERE nombre=? AND password=?",
            (nombre, password)
        )
        usuario = cursor.fetchone()

        if usuario:
            session["usuario"] = usuario["nombre"]
            session["expediente"] = usuario["expediente"]
            return redirect("/encuesta")
        else:
            flash("Usuario o contraseña incorrectos", "error")

    return render_template("login.html")

# ------------------- REGISTRO -------------------

@app.route("/", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form["nombre"]
        password = request.form["password"]
        carrera = request.form["carrera"]

        cursor = db.cursor()
        cursor.execute(
            "SELECT * FROM usuarios WHERE nombre=? AND carrera=?",
            (nombre, carrera)
        )
        existe = cursor.fetchone()

        if existe:
            flash("⚠️ Usuario ya registrado", "warning")
            return redirect("/login")

        prefijo = PREFIJOS.get(carrera, "XXX")

        cursor.execute(
            "SELECT expediente FROM usuarios WHERE carrera=? ORDER BY expediente DESC LIMIT 1",
            (carrera,)
        )
        row = cursor.fetchone()

        ultimo = int(row["expediente"][len(prefijo):]) if row else 0
        expediente = f"{prefijo}{str(ultimo + 1).zfill(2)}"

        cursor.execute(
            "INSERT INTO usuarios (nombre,password,carrera,expediente) VALUES (?,?,?,?)",
            (nombre, password, carrera, expediente)
        )
        db.commit()

        flash(f"✅ Registro exitoso. Tu expediente es {expediente}", "success")
        return redirect("/login")

    return render_template("registro.html")

# ------------------- ENCUESTA -------------------

@app.route("/encuesta", methods=["GET", "POST"])
def encuesta():
    if "usuario" not in session:
        return redirect("/login")

    if request.method == "POST":
        respuesta = request.form["respuesta"]

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO encuesta_salud (expediente,respuesta) VALUES (?,?)",
            (session["expediente"], respuesta)
        )
        db.commit()

        return redirect("/examen")

    return render_template("encuesta.html", usuario=session["usuario"])

# ------------------- EXAMEN -------------------

@app.route("/examen", methods=["GET", "POST"])
def examen():
    if "usuario" not in session:
        return redirect("/login")

    if request.method == "POST":
        formulario = dict(request.form)
        formulario["expediente"] = session["expediente"]
        formulario["fecha"] = datetime.now().strftime("%d/%m/%Y %H:%M")

        nombre_pdf = generar_pdf_examen(formulario, session["expediente"])

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO examenes (expediente, documento) VALUES (?,?)",
            (session["expediente"], nombre_pdf)
        )
        db.commit()

        return "✅ Examen enviado y PDF generado correctamente"

    return render_template(
        "examen.html",
        usuario=session["usuario"],
        expediente=session["expediente"]
    )

# ------------------- LOGOUT -------------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ------------------- RUN -------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
