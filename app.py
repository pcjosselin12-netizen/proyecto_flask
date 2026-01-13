from flask import Flask, render_template, request, redirect, session, flash
import mysql.connector
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

# ------------------- BD -------------------

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="serviciomed"
)

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

    # Título
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "EXAMEN MEDICO 2025-2", ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=9)

    for campo, valor in formulario.items():
        campo = campo.replace("_", " ").capitalize()
        texto = str(valor).replace("\n", " ").replace("\r", " ")

        # Campo + valor juntos
        linea = f"{campo}: {texto}"

        pdf.multi_cell(ancho_util, 5, linea)
        pdf.ln(1)  # espacio mínimo entre campos

    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_pdf = f"examen_{expediente}_{fecha}.pdf"
    ruta = os.path.join("examenes", nombre_pdf)

    pdf.output(ruta)
    return nombre_pdf


# ------------------- LOGIN -------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nombre = request.form["nombre"]
        password = request.form["password"]

        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM usuarios WHERE nombre=%s AND password=%s",
            (nombre, password)
        )
        usuario = cursor.fetchone()
        cursor.close()

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

        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM usuarios WHERE nombre=%s AND carrera=%s",
            (nombre, carrera)
        )
        existe = cursor.fetchone()
        cursor.close()

        if existe:
            flash("⚠️ Usuario ya registrado", "warning")
            return redirect("/login")

        prefijo = PREFIJOS.get(carrera, "XXX")

        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT expediente FROM usuarios WHERE carrera=%s ORDER BY expediente DESC LIMIT 1",
            (carrera,)
        )
        row = cursor.fetchone()
        cursor.close()

        ultimo = int(row["expediente"][len(prefijo):]) if row else 0
        expediente = f"{prefijo}{str(ultimo + 1).zfill(2)}"

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO usuarios (nombre,password,carrera,expediente) VALUES (%s,%s,%s,%s)",
            (nombre, password, carrera, expediente)
        )
        db.commit()
        cursor.close()

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
            "INSERT INTO encuesta_salud (expediente,respuesta) VALUES (%s,%s)",
            (session["expediente"], respuesta)
        )
        db.commit()
        cursor.close()

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
            "INSERT INTO examenes (expediente, documento) VALUES (%s,%s)",
            (session["expediente"], nombre_pdf)
        )
        db.commit()
        cursor.close()

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
    app.run(debug=True)
