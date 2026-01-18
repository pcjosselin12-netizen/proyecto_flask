from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import psycopg2
import os
from fpdf import FPDF
from datetime import datetime
from werkzeug.utils import secure_filename
from supabase import create_client

# ------------------- SUPABASE -------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL") or "https://ubaiixwrthqqnsuxpsbh.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InViYWlpeHdydGhxcW5zdXhwc2JoIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2ODc1MTk5NSwiZXhwIjoyMDg0MzI3OTk1fQ.cb9ttv0qEq1F7pC03_KuoCqMtkcd6HeQaAm0Qrjzho4"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------- APP -------------------
app = Flask(__name__)
app.secret_key = "1234"

PDF_FOLDER = 'examenes'
os.makedirs(PDF_FOLDER, exist_ok=True)

# ------------------- ENTORNO -------------------
IS_RENDER = os.environ.get("DATABASE_URL") is not None

# ------------------- DB -------------------
def get_db_connection():
    if IS_RENDER:
        return psycopg2.connect(os.environ.get("DATABASE_URL"), sslmode="require")
    else:
        conn = sqlite3.connect("serviciomed.db")
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(sqlite_query, postgres_query, params=(), fetchone=False, fetchall=False):
    conn = get_db_connection()
    if IS_RENDER:
        cursor = conn.cursor()
        cursor.execute(postgres_query, params)
        result = cursor.fetchone() if fetchone else cursor.fetchall() if fetchall else None
        conn.commit()
        cursor.close()
        conn.close()
        return result
    else:
        cursor = conn.execute(sqlite_query, params)
        result = cursor.fetchone() if fetchone else cursor.fetchall() if fetchall else None
        conn.commit()
        conn.close()
        return result

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
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "EXAMEN MEDICO 2025-2", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", size=9)
    for campo, valor in formulario.items():
        pdf.multi_cell(0, 5, f"{campo}: {valor}")
    nombre_pdf = f"examen_{expediente}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(os.path.join(PDF_FOLDER, nombre_pdf))
    return nombre_pdf

# ------------------- LOGIN -------------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        nombre = request.form["nombre"]
        password = request.form["password"]
        usuario = execute_query(
            "SELECT * FROM usuarios WHERE nombre=? AND password=?",
            "SELECT * FROM usuarios WHERE nombre=%s AND password=%s",
            (nombre, password),
            fetchone=True
        )
        if usuario:
            session["usuario"] = usuario["nombre"] if not IS_RENDER else usuario[1]
            session["expediente"] = usuario["expediente"] if not IS_RENDER else usuario[4]
            flash(f"Bienvenido {session['usuario']} - Expediente: {session['expediente']}", "success")
            return redirect("/encuesta")
        flash("Usuario o contraseña incorrectos", "error")
    return render_template("login.html")

# ------------------- REGISTRO -------------------
@app.route("/", methods=["GET","POST"])
def registro():
    if request.method == "POST":
        nombre = request.form["nombre"]
        password = request.form["password"]
        carrera = request.form["carrera"]
        prefijo = PREFIJOS.get(carrera, "XXX")
        ultimo = execute_query(
            "SELECT expediente FROM usuarios WHERE carrera=? ORDER BY expediente DESC LIMIT 1",
            "SELECT expediente FROM usuarios WHERE carrera=%s ORDER BY expediente DESC LIMIT 1",
            (carrera,),
            fetchone=True
        )
        ultimo_num = int(ultimo[0][len(prefijo):]) if ultimo else 0
        expediente = f"{prefijo}{str(ultimo_num + 1).zfill(2)}"
        execute_query(
            "INSERT INTO usuarios (nombre,password,carrera,expediente) VALUES (?,?,?,?)",
            "INSERT INTO usuarios (nombre,password,carrera,expediente) VALUES (%s,%s,%s,%s)",
            (nombre, password, carrera, expediente)
        )
        flash(f"✅ Registro exitoso. Tu expediente es {expediente}", "success")
        return redirect("/login")
    return render_template("registro.html")

# ------------------- ENCUESTA -------------------
@app.route("/encuesta", methods=["GET","POST"])
def encuesta():
    if "usuario" not in session:
        return redirect("/login")
    if request.method == "POST":
        respuesta = request.form["respuesta"]
        execute_query(
            "INSERT INTO encuesta_salud (expediente,respuesta) VALUES (?,?)",
            "INSERT INTO encuesta_salud (expediente,respuesta) VALUES (%s,%s)",
            (session["expediente"], respuesta)
        )
        flash(f"Gracias {session['usuario']}, tu encuesta ha sido registrada.", "success")
        return redirect("/examen")
    return render_template("encuesta.html", usuario=session["usuario"], expediente=session["expediente"])

# ------------------- EXAMEN -------------------
@app.route("/examen", methods=["GET","POST"])
def examen():
    if "usuario" not in session:
        return redirect("/login")
    if request.method == "POST":
        nombre_pdf = generar_pdf_examen(request.form, session["expediente"])
        execute_query(
            "INSERT INTO examenes (expediente,documento,fecha) VALUES (?,?,?)",
            "INSERT INTO examenes (expediente,documento,fecha) VALUES (%s,%s,%s)",
            (session["expediente"], nombre_pdf, datetime.now())
        )
        flash(f"✅ Examen generado correctamente: {nombre_pdf}", "success")
        return redirect("/subir_pdf")
    return render_template("examen.html", usuario=session["usuario"], expediente=session["expediente"])

# ------------------- SUBIR PDF -------------------
@app.route("/subir_pdf", methods=["GET","POST"])
def subir_pdf():
    if "usuario" not in session:
        return redirect("/login")
    if request.method == "POST":
        archivo = request.files["archivo"]
        nombre_original = secure_filename(archivo.filename)
        nombre_archivo = f"{session['expediente']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{nombre_original}"
        ruta = f"{session['expediente']}/{nombre_archivo}"
        supabase.storage.from_("documentos").upload(
            ruta,
            archivo.read(),
            {"content-type": "application/pdf"}
        )
        execute_query(
            "INSERT INTO documentos_subidos (expediente,nombre_original,nombre_archivo,ruta,fecha) VALUES (?,?,?,?,?)",
            "INSERT INTO documentos_subidos (expediente,nombre_original,nombre_archivo,ruta,fecha) VALUES (%s,%s,%s,%s,%s)",
            (session["expediente"], nombre_original, nombre_archivo, ruta, datetime.now())
        )
        flash(f"✅ Archivo '{nombre_original}' subido correctamente", "success")
        return redirect("/mis_documentos")
    return render_template("subir_pdf.html", usuario=session["usuario"], expediente=session["expediente"])

# ------------------- MIS DOCUMENTOS -------------------
@app.route("/mis_documentos")
def mis_documentos():
    if "usuario" not in session:
        return redirect("/login")
    documentos = execute_query(
        "SELECT * FROM documentos_subidos WHERE expediente=? ORDER BY fecha DESC",
        "SELECT * FROM documentos_subidos WHERE expediente=%s ORDER BY fecha DESC",
        (session["expediente"],),
        fetchall=True
    )
    return render_template("mis_documentos.html", documentos=documentos, usuario=session["usuario"], expediente=session["expediente"])

# ------------------- DESCARGA SEGURA -------------------
@app.route("/descargar_privado/<int:id>")
def descargar_privado(id):
    doc = execute_query(
        "SELECT ruta FROM documentos_subidos WHERE id=? AND expediente=?",
        "SELECT ruta FROM documentos_subidos WHERE id=%s AND expediente=%s",
        (id, session["expediente"]),
        fetchone=True
    )
    if not doc:
        flash("❌ No tienes permisos para descargar este archivo", "error")
        return redirect("/mis_documentos")
    signed = supabase.storage.from_("documentos").create_signed_url(doc[0], 300)
    return redirect(signed["signedURL"])

# ------------------- LOGOUT -------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ------------------- RUN -------------------
if __name__ == "__main__":
    app.run(debug=True)
