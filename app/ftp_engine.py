import ftplib
import os
import io
import zipfile
import re
import paramiko
import stat

class FTPManager:
    def __init__(self, host, user, password, protocol='ftp', port=None):
        self.host = host
        self.user = user
        self.password = password
        self.protocol = protocol.lower() if protocol else 'ftp'
        if port is not None:
            try:
                self.port = int(port)
            except ValueError:
                self.port = None
        else:
            self.port = None
        self.ftp = None
        self.ssh = None
        self.sftp = None

    def connect(self):
        if self.protocol == 'sftp':
            port = self.port if self.port is not None else 22
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(self.host, port=port, username=self.user, password=self.password, timeout=10)
            self.sftp = self.ssh.open_sftp()
        else:
            port = self.port if self.port is not None else 21
            self.ftp = ftplib.FTP()
            self.ftp.connect(self.host, port=port, timeout=10)
            self.ftp.login(self.user, self.password)
            self.ftp.voidcmd('TYPE I')

    def disconnect(self):
        if self.protocol == 'sftp':
            if self.sftp:
                try:
                    self.sftp.close()
                except:
                    pass
            if self.ssh:
                try:
                    self.ssh.close()
                except:
                    pass
        else:
            if self.ftp:
                try:
                    self.ftp.quit()
                except:
                    self.ftp.close()

    def list_disks(self):
        """Devuelve las letras de unidades disponibles escaneando discos predefinidos."""
        disks = []
        if self.protocol == 'sftp':
            for drive in ['C', 'F', 'R', 'E', 'D', 'G', 'U', 'V', 'W', 'Z']:
                try:
                    self.sftp.chdir(f"{drive}:/")
                    disks.append({'name': f"{drive}:", 'path': f"{drive}:/", 'is_dir': True})
                except Exception:
                    continue
            if not disks:
                try:
                    self.sftp.chdir('/')
                    disks.append({'name': '/', 'path': '/', 'is_dir': True})
                except Exception:
                    pass
            return disks
        else:
            for drive in ['C', 'F', 'R', 'E', 'D', 'G', 'U', 'V', 'W', 'Z']:
                try:
                    self.ftp.cwd(f"{drive}:/")
                    disks.append({'name': f"{drive}:", 'path': f"{drive}:/", 'is_dir': True})
                except ftplib.error_perm:
                    continue
                except Exception:
                    continue
            return disks

    def _parse_list_line(self, line):
        """Intenta parsear una linea generica de un LIST de un FTP ignorando metadatos base."""
        line = line.strip()
        if not line: return None
        
        # Ignorar headers y footers basura caracteristicos de DOS
        line_lower = line.lower()
        if line_lower.startswith("volume in drive") or line_lower.startswith("directory of"):
            return None
        if "file(s)" in line_lower or "dir(s)" in line_lower or "bytes free" in line_lower or "kb free" in line_lower:
            return None
            
        parts = line.split()
        if len(parts) >= 4:
            # Buscar dinamicamente la posicion de la fecha (xx-xx-xx o xx/xx/xx)
            date_idx = -1
            for i, p in enumerate(parts):
                if re.match(r'^\d{1,2}[\-\/]\d{1,2}[\-\/]\d{2,4}$', p):
                    date_idx = i
                    break
                    
            if date_idx != -1 and len(parts) > date_idx + 1:
                # El nombre siempre empieza despues de la hora (date_idx + 2)
                name = " ".join(parts[date_idx + 2:])
                # Si antes de la fecha dice DIR, es carpeta
                is_dir = any(parts[i] == 'DIR' for i in range(date_idx))
                
                if not name or name in ('.', '..'): 
                    return None
                return {'is_dir': is_dir, 'name': name}

        # 1. Formato DOS clásico (Fallback)
        match_dos = re.match(r'^(\d{1,2}[\-\/]\d{1,2}[\-\/]\d{2,4})\s+([\d:]+[a-zA-Z]{0,2})\s+(<DIR>|[\d,\.]+)?\s+(.+)$', line, re.IGNORECASE)
        if match_dos:
            dir_or_size = (match_dos.group(3) or '').upper()
            is_dir = ('<DIR>' in dir_or_size)
            name = match_dos.group(4).strip()
            if name in ('.', '..'): return None
            return {'is_dir': is_dir, 'name': name}
            
        # 2. Formato Unix (Fallback)
        if re.match(r'^[dl\-][rwx\-stST]{9}', line):
            if len(parts) >= 8:
                name = " ".join(parts[8:]) if (":" in parts[-2] or parts[-2].isdigit()) else " ".join(parts[8:])
                if not name and len(parts) > 0: name = parts[-1]
                is_dir = line.startswith('d')
                if name in ('.', '..'): return None
                return {'is_dir': is_dir, 'name': name}
                
        return None

    def list_dir(self, path):
        """Lista el contenido de un directorio usando LIST o NLST_Fallback, o listdir_attr para SFTP."""
        if self.protocol == 'sftp':
            items = []
            try:
                for attr in self.sftp.listdir_attr(path):
                    name = attr.filename
                    if name in ('.', '..'):
                        continue
                    clean_path = path.rstrip('/')
                    if clean_path:
                        target_path = f"{clean_path}/{name}"
                    else:
                        target_path = f"/{name}"
                    is_dir = stat.S_ISDIR(attr.st_mode)
                    items.append({
                        'name': name,
                        'path': target_path,
                        'is_dir': is_dir
                    })
            except Exception as e:
                log_file = os.path.join(os.path.dirname(__file__), '..', 'ftp_debug.log')
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n[SFTP LIST_DIR ERROR] Path: {path}, Error: {str(e)}\n")
                raise e
            return items

        if path:
            self.ftp.cwd(path)
        items = []
        
        # LOGGING PARA DEBUG DE FORMATOS TOSHIBA 4690
        log_file = os.path.join(os.path.dirname(__file__), '..', 'ftp_debug.log')
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n--- EXPLORANDO: {path} ---\n")
            
            lines = []
            try:
                self.ftp.retrlines('LIST', lines.append)
                f.write("OUTPUT DE LIST:\n")
                for l in lines: f.write(l + "\n")
                
                parsed_items = []
                for line in lines:
                    info = self._parse_list_line(line)
                    if info:
                        info['path'] = f"{path.rstrip('/')}/{info['name']}"
                        parsed_items.append(info)
                    else:
                        f.write(f"[RECHAZADA X REGEX]: {line}\n")
                        
                if parsed_items:
                    f.write("-> LIST PARSEADO CON EXITO, EVITANDO NLST.\n")
                    return parsed_items
            except Exception as e:
                f.write(f"-> EXCEPCION EN LIST: {e}\n")
            
            f.write("-> CAYENDO A NLST FALLBACK...\n")
            
            # Fallback a NLST
            try:
                names = self.ftp.nlst()
                f.write("OUTPUT DE NLST:\n")
                for raw_name in names: f.write(raw_name + "\n")
                
                for raw_name in names:
                    name = raw_name.replace('\\', '/').split('/')[-1]
                    if not name or name in ('.', '..'): continue
                    
                    target_path = f"{path.rstrip('/')}/{name}"
                    is_dir = True # Por defecto asumimos directorio
                    
                    # El hack maestro para Toshiba: usar SIZE en lugar de CWD.
                    # FTP 'SIZE' usualmente falla devolviendo "550 Not a plain file" si es un directorio.
                    # Si devuelve un número, es 100% un archivo (ej: .jar, .dat, .txt)
                    try:
                        self.ftp.size(target_path)
                        is_dir = False # Confirmado: es archivo
                    except:
                        is_dir = True # Si falla SIZE, asumimos que es carpeta
                        
                    items.append({
                        'name': name,
                        'path': target_path,
                        'is_dir': is_dir
                    })
            except Exception as e:
                f.write(f"-> EXCEPCION EN NLST: {e}\n")
            
        return items

    def upload(self, local_file_obj, remote_path):
        """Sube un archivo asumiendo que transferimos binario."""
        if self.protocol == 'sftp':
            self.sftp.putfo(local_file_obj, remote_path)
        else:
            self.ftp.storbinary(f"STOR {remote_path}", local_file_obj)

    def download(self, remote_path):
        """Descarga un archivo en un BytesIO en memoria y lo devuelve."""
        file_obj = io.BytesIO()
        if self.protocol == 'sftp':
            self.sftp.getfo(remote_path, file_obj)
            file_obj.seek(0)
        else:
            self.ftp.retrbinary(f"RETR {remote_path}", file_obj.write)
            file_obj.seek(0)
        return file_obj

    def delete(self, remote_path):
        """Elimina archivo o directorio de forma recursiva con logging detallado."""
        log_file = os.path.join(os.path.dirname(__file__), '..', 'ftp_debug.log')
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n--- SOLICITUD DE BORRADO: {remote_path} (protocol={self.protocol}) ---\n")
            
        if self.protocol == 'sftp':
            is_dir = False
            try:
                stat_val = self.sftp.stat(remote_path)
                is_dir = stat.S_ISDIR(stat_val.st_mode)
            except Exception:
                pass
                
            if is_dir:
                try:
                    self._delete_recursive_sftp(remote_path)
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"-> Borrado recursivo SFTP completado para {remote_path}\n")
                except Exception as e:
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"-> ERROR CRITICO en borrado recursivo SFTP: {e}\n")
                    raise e
            else:
                try:
                    self.sftp.remove(remote_path)
                except Exception as e:
                    try:
                        self.sftp.rmdir(remote_path)
                    except:
                        raise e
            return

        # Determinamos si es directorio intentando CWD
        is_dir = False
        try:
            # El hack de SIZE es más rápido pero CWD es más seguro para confirmar carpeta
            self.ftp.cwd(remote_path)
            is_dir = True
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"-> Es un directorio (CWD exitoso)\n")
            # Volvemos a la raíz o un nivel arriba no es fácil sin PWD, 
            # pero list_dir hará su propio CWD.
        except Exception as e:
            is_dir = False
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"-> No es un directorio o no se puede acceder (CWD fallo): {e}\n")

        if is_dir:
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    self._delete_recursive(remote_path, f)
                    f.write(f"-> Borrado recursivo completado para {remote_path}\n")
            except Exception as e:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"-> ERROR CRITICO en borrado recursivo: {e}\n")
                raise e
        else:
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"-> Intentando DELE {remote_path}\n")
                self.ftp.delete(remote_path)
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"-> DELE exitoso\n")
            except Exception as e:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"-> DELE fallo: {e}\n")
                # Si DELE fallo, intentamos RMD por si acaso era una carpeta vacía que CWD no detectó
                try:
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"-> Intentando RMD directo como fallback\n")
                    self.ftp.rmd(remote_path)
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"-> RMD exitoso\n")
                except:
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"-> RMD fallback también falló\n")
                    raise e

    def _delete_recursive_sftp(self, remote_path):
        """Helper para navegar y borrar todo el contenido de una carpeta en SFTP."""
        for attr in self.sftp.listdir_attr(remote_path):
            name = attr.filename
            if name in ('.', '..'):
                continue
            
            clean_path = remote_path.rstrip('/')
            if clean_path:
                item_path = f"{clean_path}/{name}"
            else:
                item_path = f"/{name}"
                
            if stat.S_ISDIR(attr.st_mode):
                self._delete_recursive_sftp(item_path)
            else:
                self.sftp.remove(item_path)
        self.sftp.rmdir(remote_path)

    def _delete_recursive(self, remote_path, log_handle):
        """Helper para navegar y borrar todo el contenido de una carpeta."""
        log_handle.write(f"   [RECURSION] Explorando: {remote_path}\n")
        items = self.list_dir(remote_path)
        log_handle.write(f"   [RECURSION] {len(items)} elementos encontrados\n")
        
        for item in items:
            if item['is_dir']:
                self._delete_recursive(item['path'], log_handle)
            else:
                try:
                    log_handle.write(f"   [RECURSION] Borrando archivo: {item['path']}\n")
                    self.ftp.delete(item['path'])
                except Exception as e:
                    log_handle.write(f"   [RECURSION] Error borrando archivo {item['path']}: {e}\n")
                    # No lanzamos excepción aquí para intentar borrar lo máximo posible
        
        # Finalmente eliminamos la carpeta que ya debería estar vacía
        try:
            log_handle.write(f"   [RECURSION] Ejecutando RMD {remote_path}\n")
            self.ftp.rmd(remote_path)
            log_handle.write(f"   [RECURSION] RMD exitoso\n")
        except Exception as e:
            log_handle.write(f"   [RECURSION] RMD falló en {remote_path}: {e}\n")
            raise e

    def rename(self, old_path, new_path):
        """Renombra."""
        if self.protocol == 'sftp':
            self.sftp.rename(old_path, new_path)
        else:
            self.ftp.rename(old_path, new_path)
        
    def make_dir(self, remote_path):
        """Crea un nuevo directorio."""
        if self.protocol == 'sftp':
            self.sftp.mkdir(remote_path)
        else:
            self.ftp.mkd(remote_path)
        
    def download_folder_zip(self, folder_path):
        """Descarga una carpeta completa y la comprime en ZIP dinámicamente."""
        memory_zip = io.BytesIO()
        base_folder_name = os.path.basename(folder_path.rstrip('/'))
        if not base_folder_name: # Casos con root like C:/
            base_folder_name = "download"
            
        with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            self._zip_folder_recursive(zf, folder_path, base_folder_name)
            
        memory_zip.seek(0)
        return memory_zip

    def _zip_folder_recursive(self, zf, current_ftp_path, current_zip_path):
        """Helper para explorar y empaquetar en el zip."""
        items = self.list_dir(current_ftp_path)
        for item in items:
            item_ftp_path = item['path']
            item_zip_path = f"{current_zip_path}/{item['name']}"
            
            if item['is_dir']:
                self._zip_folder_recursive(zf, item_ftp_path, item_zip_path)
            else:
                try:
                    file_obj = self.download(item_ftp_path)
                    zf.writestr(item_zip_path, file_obj.read())
                except Exception as e:
                    print(f"No se pudo descargar {item_ftp_path} para comprimir: {e}")
