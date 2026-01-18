from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import psycopg2
import os
from fpdf import FPDF
from datetime import datetime
from werkzeug.utils import secure_filename
from supabase import create_client
from dotenv import load_dotenv

# ------------------- CARGAR VARIABLES DE ENTORNO -------------------
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY", "1234")  # default

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("❌ Debes definir SUPABASE_URL y SUPABASE_KEY como variables de entorno")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------- APP -------------------
app = Flask(__name__)
app.secret_key = SECRET_KEY

PDF_FOLDER = 'temp_pdfs'
os.makedirs(PDF_FOLDER, exist_ok=True)

# ------------------- ENTORNO -------------------
IS_RENDER = os.environ.get("DATABASE_URL") is not None

# ------------------- DB -------------------
def get_db_connection():
    if IS_RENDER:
        database_url = os.environ.get("DATABASE_URL")
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(database_url, sslmode="require")
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

# ------------------- FUNCIONES PDF -------------------
def clean_text(text):
    if not text:
        return ""
    return ''.join(c if ord(c) < 128 else '?' for c in str(text))

def generar_pdf_examen(formulario, expediente):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 8, "EXAMEN MEDICO 2025-2", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Arial", size=9)
    for campo, valor in formulario.items():
        pdf.multi_cell(180, 5, f"{campo}: {clean_text(valor)}")
    nombre_pdf = f"examen_{expediente}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    ruta_local = os.path.join(PDF_FOLDER, nombre_pdf)
    pdf.output(ruta_local)
    return nombre_pdf, ruta_local

# ------------------- RUTAS -------------------

# LOGIN
@app.route("/login", methods=["GET", "POST"])
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

# REGISTRO
@app.route("/", methods=["GET", "POST"])
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

# ENCUESTA
@app.route("/encuesta", methods=["GET", "POST"])
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

# EXAMEN
@app.route("/examen", methods=["GET", "POST"])
def examen():
    if "usuario" not in session:
        return redirect("/login")
    if request.method == "POST":
        nombre_pdf, ruta_local = generar_pdf_examen(request.form, session["expediente"])
        ruta_supabase = f"{session['expediente']}/{nombre_pdf}"
        try:
            with open(ruta_local, "rb") as f:
                supabase.storage.from_("documentos").upload(ruta_supabase, f.read(), {"content-type": "application/pdf"})
            os.remove(ruta_local)
        except Exception as e:
            flash(f"❌ Error al subir el PDF a Supabase: {e}", "error")
            return redirect("/examen")
        execute_query(
            "INSERT INTO examenes (expediente,documento,fecha) VALUES (?,?,?)",
            "INSERT INTO examenes (expediente,documento,fecha) VALUES (%s,%s,%s)",
            (session["expediente"], ruta_supabase, datetime.now())
        )
        flash(f"✅ Examen generado y subido correctamente: {nombre_pdf}", "success")
        return redirect("/mis_documentos")
    return render_template("examen.html", usuario=session["usuario"], expediente=session["expediente"])

# SUBIR PDF
@app.route("/subir_pdf", methods=["GET", "POST"])
def subir_pdf():
    if "usuario" not in session:
        return redirect("/login")
    if request.method == "POST":
        archivo = request.files.get("archivo")
        if not archivo or archivo.filename == "":
            flash("❌ No se seleccionó ningún archivo", "error")
            return redirect("/subir_pdf")

        nombre_seguro = secure_filename(archivo.filename)
        ruta_local = os.path.join(PDF_FOLDER, nombre_seguro)
        archivo.save(ruta_local)

        ruta_supabase = f"{session['expediente']}/{nombre_seguro}"
        try:
            with open(ruta_local, "rb") as f:
                supabase.storage.from_("documentos").upload(ruta_supabase, f.read(), {"content-type": "application/pdf"})
            os.remove(ruta_local)
        except Exception as e:
            flash(f"❌ Error al subir el PDF a Supabase: {e}", "error")
            return redirect("/subir_pdf")

        execute_query(
            "INSERT INTO examenes (expediente,documento,fecha) VALUES (?,?,?)",
            "INSERT INTO examenes (expediente,documento,fecha) VALUES (%s,%s,%s)",
            (session["expediente"], ruta_supabase, datetime.now())
        )
        flash(f"✅ PDF subido correctamente: {nombre_seguro}", "success")
        return redirect("/mis_documentos")

    return render_template("subir_pdf.html", usuario=session["usuario"], expediente=session["expediente"])

# MIS DOCUMENTOS
@app.route("/mis_documentos")
def mis_documentos():
    if "usuario" not in session:
        return redirect("/login")
    documentos = execute_query(
        "SELECT * FROM examenes WHERE expediente=? ORDER BY fecha DESC",
        "SELECT * FROM examenes WHERE expediente=%s ORDER BY fecha DESC",
        (session["expediente"],),
        fetchall=True
    )
    return render_template("mis_documentos.html", documentos=documentos, usuario=session["usuario"], expediente=session["expediente"])

# DESCARGA PDF PRIVADA
@app.route("/descargar_privado/<path:ruta>")
def descargar_privado(ruta):
    try:
        signed = supabase.storage.from_("documentos").create_signed_url(ruta, 3600)
        return redirect(signed["signedURL"])
    except Exception as e:
        flash(f"❌ Error al generar URL de descarga: {e}", "error")
        return redirect("/mis_documentos")

# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ------------------- RUN -------------------
if __name__ == "__main__":
    app.run(debug=True)
