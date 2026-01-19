from flask import Flask, render_template, request, redirect, session, flash, send_from_directory
import sqlite3
import psycopg2
import os
from fpdf import FPDF
from datetime import datetime
from werkzeug.utils import secure_filename
from supabase import create_client

# ------------------- APP -------------------

app = Flask(__name__)
app.secret_key = "1234"

UPLOAD_FOLDER = 'uploads'
PDF_FOLDER = 'examenes'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ------------------- SUPABASE -------------------

SUPABASE_URL = "https://ubaiixwrthqqnsuxpsbh.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InViYWlpeHdydGhxcW5zdXhwc2JoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njg3NTE5OTUsImV4cCI6MjA4NDMyNzk5NX0.u5n5R1i0OdyeOF5iWEr14l4ijXtRvlmIZOhBuvmKnO8"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------- ENTORNO -------------------

IS_RENDER = os.environ.get("DATABASE_URL") is not None

# ------------------- DB -------------------

def get_db_connection():
    if IS_RENDER:
        return psycopg2.connect(
            os.environ.get("DATABASE_URL"),
            sslmode="require"
        )
    else:
        conn = sqlite3.connect("serviciomed.db")
        conn.row_factory = sqlite3.Row
        return conn


def execute_query(sqlite_query, postgres_query, params=(), fetchone=False, fetchall=False):
    conn = get_db_connection()

    if IS_RENDER:
        cursor = conn.cursor()
        cursor.execute(postgres_query, params)

        result = None
        if fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()

        conn.commit()
        cursor.close()
        conn.close()
        return result
    else:
        cursor = conn.execute(sqlite_query, params)

        result = None
        if fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()

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

# ------------------- SUPABASE PDF -------------------
def subir_pdf_supabase(ruta_local, nombre_archivo, expediente):
    with open(ruta_local, "rb") as f:
        supabase.storage.from_("pdfs").upload(
            f"{expediente}/{nombre_archivo}",
            f
        )

    return f"{SUPABASE_URL}/storage/v1/object/public/pdfs/{expediente}/{nombre_archivo}"



# ------------------- PDF EXAMEN -------------------

def generar_pdf_examen(formulario, expediente):
    pdf = FPDF()
    pdf.set_margins(12, 12, 12)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=12)

    ancho = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "EXAMEN MEDICO 2025-2", ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=9)
    for campo, valor in formulario.items():
        campo = campo.replace("_", " ").capitalize()
        pdf.multi_cell(ancho, 5, f"{campo}: {valor}")
        pdf.ln(1)

   
    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_pdf = f"{session['expediente']}_examen_{fecha}.pdf"
     # 📁 Guardar temporal
    os.makedirs(PDF_FOLDER, exist_ok=True)
    ruta_pdf = os.path.join(PDF_FOLDER, nombre_pdf)
    pdf.output(ruta_pdf)

    return nombre_pdf, ruta_pdf

    
    

# ------------------- LOGIN -------------------

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
            session["usuario"] = usuario[1] if IS_RENDER else usuario["nombre"]
            session["expediente"] = usuario[4] if IS_RENDER else usuario["expediente"]
            return redirect("/encuesta")

        flash("Usuario o contraseña incorrectos", "error")

    return render_template("login.html")

# ------------------- REGISTRO -------------------

@app.route("/", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form["nombre"]
        password = request.form["password"]
        carrera = request.form["carrera"]

        existe = execute_query(
            "SELECT * FROM usuarios WHERE nombre=? AND carrera=?",
            "SELECT * FROM usuarios WHERE nombre=%s AND carrera=%s",
            (nombre, carrera),
            fetchone=True
        )

        if existe:
            flash("⚠️ Usuario ya registrado", "warning")
            return redirect("/login")

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

        # 1️⃣ Generar PDF local
        nombre_pdf, ruta_pdf = generar_pdf_examen(
    formulario,
    session["expediente"]
)
       


        # 2️⃣ Subir UNA SOLA VEZ a Supabase
        url_supabase = subir_examen_supabase(
    ruta_pdf,
    nombre_pdf,
    session["expediente"]
)

        # 3️⃣ Guardar en BD
        execute_query(
            "INSERT INTO examenes (expediente, documento, url, fecha) VALUES (?, ?, ?, ?)",
            "INSERT INTO examenes (expediente, documento, url, fecha) VALUES (%s, %s, %s, %s)",
            (
                session["expediente"],
                nombre_pdf,
                url_supabase,
                datetime.now()
            )
        )

        # 4️⃣ Borrar local
        os.remove(ruta_pdf)

        flash("✅ Examen generado y guardado correctamente", "success")
        return redirect("/mis_documentos")

    return render_template("examen.html", usuario=session["usuario"])



# ------------------- SUBIR PDF -------------------

@app.route("/subir_pdf", methods=["GET", "POST"])
def subir_pdf():
    if "usuario" not in session:
        return redirect("/login")

    if request.method == "POST":
        archivo = request.files.get("archivo")

        # 1️⃣ Validaciones básicas
        if archivo is None or archivo.filename == "":
            flash("❌ No se seleccionó archivo", "error")
            return redirect("/subir_pdf")

        if not archivo.filename.lower().endswith(".pdf"):
            flash("❌ Solo se permiten archivos PDF", "error")
            return redirect("/subir_pdf")

        # 2️⃣ Preparar nombre del archivo
        nombre_original = secure_filename(archivo.filename)
        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"{session['expediente']}_{fecha}_{nombre_original}"

        # 3️⃣ Guardar archivo temporal
        carpeta_temp = "temp_pdfs"
        os.makedirs(carpeta_temp, exist_ok=True)
        ruta_temp = os.path.join(carpeta_temp, nombre_archivo)
        archivo.save(ruta_temp)

        try:
            # 4️⃣ Subir a Supabase
            url_supabase = subir_pdf_supabase(
                ruta_temp,
                nombre_archivo,
                session["expediente"]
            )

            # 5️⃣ Guardar registro en BD
            execute_query(
                "INSERT INTO documentos_subidos (expediente, nombre_archivo, nombre_original, url,  fecha) VALUES (?, ?, ?, ?, ?)",
                "INSERT INTO documentos_subidos (expediente, nombre_archivo, nombre_original, url, fecha) VALUES (%s, %s, %s, %s, %s)",
                (
                    session["expediente"],
                    nombre_archivo,
                    nombre_original,
                    url_supabase,
                    datetime.now()
                )
            )

            flash("✅ Documento subido correctamente", "success")

        except Exception as e:
            print("ERROR SUPABASE:", e)  # ← MUY IMPORTANTE PARA DEPURAR
            flash("❌ Error al subir el documento", "error")

        finally:
            # 6️⃣ Borrar archivo temporal
            if os.path.exists(ruta_temp):
                os.remove(ruta_temp)

        return redirect("/mis_documentos")

    # GET
    return render_template(
        "subir_pdf.html",
        usuario=session.get("usuario"),
        expediente=session.get("expediente")
    )


# ------------------- MIS DOCUMENTOS -------------------
@app.route("/mis_documentos")
def mis_documentos():
    if "usuario" not in session:
        return redirect("/login")

    documentos = execute_query(
        "SELECT nombre_original, url, fecha FROM documentos_subidos WHERE expediente=?",
        "SELECT nombre_original, url, fecha FROM documentos_subidos WHERE expediente=%s",
        (session["expediente"],),
        fetchall=True
    )

    examenes = execute_query(
        "SELECT documento, url, fecha FROM examenes WHERE expediente=?",
        "SELECT documento, url, fecha FROM examenes WHERE expediente=%s",
        (session["expediente"],),
        fetchall=True
    )

    return render_template(
        "mis_documentos.html",
        documentos=documentos,
        examenes=examenes,
        usuario=session["usuario"],
        expediente=session["expediente"]
    )

# ------------------- DESCARGAS -------------------

@app.route("/descargar/<archivo>")
def descargar_pdf(archivo):
    return send_from_directory(PDF_FOLDER, archivo, as_attachment=True)

@app.route("/descargar_subido/<archivo>")
def descargar_pdf_subido(archivo):
    return send_from_directory(UPLOAD_FOLDER, archivo, as_attachment=True)

# ------------------- subir_examen supabase -------------------
def subir_examen_supabase(ruta_local, nombre_archivo, expediente):
    with open(ruta_local, "rb") as f:
        supabase.storage.from_("pdfs").upload(
            f"{expediente}/{nombre_archivo}",
            f,
            {"content-type": "application/pdf"}
        )

    return f"{SUPABASE_URL}/storage/v1/object/public/pdfs/{expediente}/{nombre_archivo}"


# ------------------- LOGOUT -------------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ------------------- RUN -------------------

if __name__ == "__main__":
    app.run(debug=True)
