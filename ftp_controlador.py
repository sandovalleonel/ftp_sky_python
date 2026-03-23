import ftplib

def detectar_discos_4690(host, user, password):
    # Definimos las unidades que ya sabes que existen
    # En 4690 a veces se listan como 'C:', 'F:', 'D:', 'R:' (RAM disk)
    unidades_a_probar = ['C', 'D', 'E', 'F', 'R']
    discos_encontrados = []

    try:
        # Añadimos timeout de 10 segundos para que no se quede colgado
        print(f"Conectando a {host} (Toshiba 4690)...")
        ftp = ftplib.FTP(host, timeout=10)
        ftp.login(user=user, passwd=password)
        
        # El 4690 suele requerir el comando TYPE A o I antes de navegar
        ftp.voidcmd('TYPE I') 

        for letra in unidades_a_probar:
            # En 4690 la sintaxis suele ser "C:" o "C:/"
            intento = f"{letra}:"
            try:
                # Usamos mandatos de bajo nivel para ver si el disco responde
                ftp.cwd(intento)
                print(f"[+] Disco detectado: {intento}")
                discos_encontrados.append(intento)
                # Regresamos a la raíz para la siguiente prueba
                ftp.cwd("/")
            except (ftplib.error_perm, ftplib.error_temp, TimeoutError):
                continue

        if not discos_encontrados:
            print("No se detectaron discos con CWD directo. Intentando listado raíz...")
            # Si falla CWD, intentamos listar la raíz para ver cómo nombra los discos
            ftp.dir()

        ftp.quit()

    except Exception as e:
        print(f"Error de conexión: {e}")

if __name__ == "__main__":
    # Reemplaza con tus credenciales
    FTP_HOST = "192.168.150.16"
    FTP_USER = "pos34"
    FTP_PASS = "pos043"

    detectar_discos_4690(FTP_HOST, FTP_USER, FTP_PASS)