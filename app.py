from flask import Flask, render_template, request, redirect, session, flash, send_from_directory
import sqlite3
import os
from fpdf import FPDF
from datetime import datetime
import smtplib
from email.message import EmailMessage


# ------------------- APP -------------------

app = Flask(__name__)
app.secret_key = "1234"

UPLOAD_FOLDER = 'uploads'
PDF_FOLDER = 'examenes'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)

# ------------------- BD -------------------

DB_FILE = "serviciomed.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

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
        linea = f"{campo}: {texto}"
        pdf.multi_cell(ancho_util, 5, linea)
        pdf.ln(1)

    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_pdf = f"examen_{expediente}_{fecha}.pdf"
    ruta = os.path.join(PDF_FOLDER, nombre_pdf)

    pdf.output(ruta)
    return nombre_pdf

def enviar_pdf_por_correo(ruta_pdf):
    email_user = os.environ.get("EMAIL_USER")
    email_pass = os.environ.get("EMAIL_PASS")

    if not email_user or not email_pass:
        print("❌ Faltan variables de entorno EMAIL_USER o EMAIL_PASS")
        return

    msg = EmailMessage()
    msg["Subject"] = "Nuevo examen médico recibido"
    msg["From"] = email_user
    msg["To"] = email_user
    msg.set_content("Se ha enviado un nuevo examen médico en PDF.")

    with open(ruta_pdf, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="pdf",
            filename=os.path.basename(ruta_pdf)
        )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_user, email_pass)
            server.send_message(msg)
        print("✅ Correo enviado correctamente")
    except Exception as e:
        print("❌ Error al enviar correo:", e)

# ------------------- LOGIN -------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nombre = request.form["nombre"]
        password = request.form["password"]

        conn = get_db_connection()
        usuario = conn.execute(
            "SELECT * FROM usuarios WHERE nombre=? AND password=?",
            (nombre, password)
        ).fetchone()
        conn.close()

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

        conn = get_db_connection()
        existe = conn.execute(
            "SELECT * FROM usuarios WHERE nombre=? AND carrera=?",
            (nombre, carrera)
        ).fetchone()

        if existe:
            flash("⚠️ Usuario ya registrado", "warning")
            conn.close()
            return redirect("/login")

        prefijo = PREFIJOS.get(carrera, "XXX")
        row = conn.execute(
            "SELECT expediente FROM usuarios WHERE carrera=? ORDER BY expediente DESC LIMIT 1",
            (carrera,)
        ).fetchone()

        ultimo = int(row["expediente"][len(prefijo):]) if row else 0
        expediente = f"{prefijo}{str(ultimo + 1).zfill(2)}"

        conn.execute(
            "INSERT INTO usuarios (nombre,password,carrera,expediente) VALUES (?,?,?,?)",
            (nombre, password, carrera, expediente)
        )
        conn.commit()
        conn.close()

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
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO encuesta_salud (expediente,respuesta) VALUES (?,?)",
            (session["expediente"], respuesta)
        )
        conn.commit()
        conn.close()
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

        ruta_pdf = os.path.join(PDF_FOLDER, nombre_pdf)
        enviar_pdf_por_correo(ruta_pdf)


        conn = get_db_connection()
        conn.execute(
            "INSERT INTO examenes (expediente, documento) VALUES (?,?)",
            (session["expediente"], nombre_pdf)
        )
        conn.commit()
        conn.close()

        # PDF solo para administrador
        return f"✅ Examen enviado y PDF generado correctamente."

    return render_template("examen.html", usuario=session["usuario"], expediente=session["expediente"])

# ------------------- DESCARGAR PDF (solo admin) -------------------

@app.route("/descargar/<nombre_pdf>")
def descargar_pdf(nombre_pdf):
    # Aquí puedes poner un control de administrador, por ejemplo:
    # if 'admin' not in session:
    #     return "No autorizado", 403
    return send_from_directory(PDF_FOLDER, nombre_pdf, as_attachment=True)

# ------------------- LOGOUT -------------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ------------------- RUN -------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
