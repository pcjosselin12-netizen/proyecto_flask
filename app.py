# bienbuena
from flask import Flask, render_template, request, redirect, session, flash, send_from_directory

import sqlite3
import os
from fpdf import FPDF
from datetime import datetime
from werkzeug.utils import secure_filename
# ------------------- APP -------------------

app = Flask(__name__)
app.secret_key = "1234"
UPLOAD_FOLDER = 'uploads'
PDF_FOLDER = 'examenes'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)
# Configurar tamaño máximo de archivo (16MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Extensiones permitidas para archivos
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    """Verifica si el archivo tiene una extensión permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ------------------- BD SQLITE -------------------

DB_FILE = "serviciomed.db"
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
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

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "EXAMEN MEDICO 2025-2", ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=9)
    for campo, valor in formulario.items():
        campo = campo.replace("_", " ").capitalize()
        texto = str(valor).replace("\n", " ").replace("\r", " ")
        pdf.multi_cell(ancho_util, 5, f"{campo}: {texto}")
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

        # Generar PDF del examen
        nombre_pdf = generar_pdf_examen(formulario, session["expediente"])
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Guardar en BD
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO examenes (expediente, documento, fecha) VALUES (?, ?, ?)",
                (session["expediente"], nombre_pdf, fecha)
            )
            conn.commit()
        finally:
            conn.close()

        # Mensaje y redirección a subir PDF
        flash("✅ Examen enviado correctamente. Ahora sube tus documentos.", "success")
        return redirect("/subir_pdf")

    return render_template(
        "examen.html",
        usuario=session["usuario"],
        expediente=session["expediente"]
    )

        
# ------------------- SUBIR PDF -------------------

@app.route("/subir_pdf", methods=["GET", "POST"])
def subir_pdf():
    if "usuario" not in session:
        return redirect("/login")

    if request.method == "POST":
        # Verificar si hay un archivo en la petición
        if 'archivo' not in request.files:
            flash("No se seleccionó ningún archivo", "error")
            return redirect("/subir_pdf")

        archivo = request.files['archivo']
        expediente = session["expediente"]

        # Si el usuario no selecciona un archivo, el navegador envía un archivo vacío
        if archivo.filename == '':
            flash("No se seleccionó ningún archivo", "error")
            return redirect("/subir_pdf")

        # Validar que sea un PDF
        if archivo and allowed_file(archivo.filename):
            try:
                # Obtener el nombre original del archivo
                nombre_original = secure_filename(archivo.filename)
                
                # Generar un nombre único para evitar conflictos
                fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
                nombre_archivo = f"{expediente}_{fecha}_{nombre_original}"
                
                # Guardar el archivo
                ruta_archivo = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo)
                archivo.save(ruta_archivo)

                # Guardar en la base de datos
                fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn = get_db_connection()
                conn.execute(
                    "INSERT INTO documentos_subidos (expediente, nombre_archivo, nombre_original, fecha) VALUES (?, ?, ?, ?)",
                    (expediente, nombre_archivo, nombre_original, fecha_actual)
                )
                conn.commit()
                conn.close()

                flash(f"✅ Archivo '{nombre_original}' subido correctamente", "success")
                return redirect("/mis_documentos")
            except Exception as e:
                flash(f"❌ Error al subir el archivo: {str(e)}", "error")
                return redirect("/subir_pdf")
        else:
            flash("❌ Solo se permiten archivos PDF", "error")
            return redirect("/subir_pdf")

    return render_template("subir_pdf.html", usuario=session["usuario"], expediente=session["expediente"])
# ------------------- MIS DOCUMENTOS -------------------

@app.route("/mis_documentos")
def mis_documentos():
    if "usuario" not in session:
        return redirect("/login")

    expediente = session["expediente"]
    conn = get_db_connection()
    
    # Obtener documentos subidos por el usuario
    try:
        documentos_subidos = conn.execute(
            "SELECT * FROM documentos_subidos WHERE expediente=? ORDER BY fecha DESC",
            (expediente,)
        ).fetchall()
    except:
        documentos_subidos = []
    
    # Obtener exámenes generados por el usuario
    try:
        examenes_generados = conn.execute(
            "SELECT * FROM examenes WHERE expediente=? ORDER BY fecha DESC",
            (expediente,)
        ).fetchall()
    except:
        examenes_generados = []
    
    conn.close()

    return render_template(
        "mis_documentos.html",
        usuario=session["usuario"],
        expediente=expediente,
        documentos_subidos=documentos_subidos,
        examenes_generados=examenes_generados
    )
# ------------------- DESCARGAR PDF -------------------

@app.route("/descargar/<archivo>")
def descargar_pdf(archivo):
    if "usuario" not in session:
        return redirect("/login")

    return send_from_directory(
        PDF_FOLDER,
        archivo,
        as_attachment=True
    )

# ------------------- DESCARGAR PDF SUBIDO -------------------

@app.route("/descargar_subido/<archivo>")
def descargar_pdf_subido(archivo):
    if "usuario" not in session:
        return redirect("/login")

    # Verificar que el archivo pertenezca al usuario
    conn = get_db_connection()
    documento = conn.execute(
        "SELECT * FROM documentos_subidos WHERE nombre_archivo=? AND expediente=?",
        (archivo, session["expediente"])
    ).fetchone()
    conn.close()

    if documento:
        return send_from_directory(
            UPLOAD_FOLDER,
            archivo,
            as_attachment=True
        )
    else:
        flash("No tienes permisos para acceder a este archivo", "error")
        return redirect("/mis_documentos")
# ------------------- LOGOUT -------------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ------------------- RUN -------------------

if __name__ == "__main__":
    print("✅ Servidor iniciando en http://127.0.0.1:5000")
    app.run(debug=True, host='127.0.0.1', port=5000)
    