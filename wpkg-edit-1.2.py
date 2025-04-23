# Améliorations et optimisations pour l'Éditeur de Paquets WPKG v1.2

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import xml.etree.ElementTree as ET
from xml.dom import minidom
from lxml import etree
import re
import os
import sys
import platform
import subprocess
import string
import json
import threading
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Union, Tuple
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor
import pygments
from pygments.lexers import XmlLexer
from pygments.formatters import HtmlFormatter
import html
import time
import datetime

# Utilisation de dataclasses pour un code plus propre et meilleur typage (Python 3.7+)
@dataclass
class Variable:
    name: str
    value: str
    architecture: str = ""

@dataclass
class Check:
    type: str
    condition: str
    path: str
    value: str = ""
    architecture: str = ""

@dataclass
class Command:
    cmd: str = ""
    include: str = ""
    timeout: str = ""
    exit_code: str = ""

@dataclass
class Package:
    id: str = ""
    name: str = ""
    revision: str = ""
    date: str = ""
    reboot: str = "false"
    category: str = ""
    priority: str = ""
    variables: List[Variable] = field(default_factory=list)
    checks: List[Check] = field(default_factory=list)
    installs: List[Command] = field(default_factory=list)
    upgrades: List[Command] = field(default_factory=list)
    removes: List[Command] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)
    xml_declaration: str = '<?xml version="1.0" encoding="iso-8859-1"?>'


class XmlTextWithLineNumbers(tk.Frame):
    """Widget Text avec numéros de ligne et coloration syntaxique pour XML avec complétion"""
    def __init__(self, master, *args, **kwargs):
        tk.Frame.__init__(self, master)
        self.text = tk.Text(self, wrap="none", *args, **kwargs)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.text.grid(row=0, column=1, sticky="nsew")
        self.vsb.grid(row=0, column=2, sticky="ns")
        self.hsb.grid(row=1, column=1, sticky="ew")
        
        self.linenumbers = tk.Canvas(self, width=30)
        self.linenumbers.grid(row=0, column=0, sticky="ns")
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # Tags pour coloration syntaxique
        self.text.tag_configure("tag", foreground="#008000")
        self.text.tag_configure("attribute", foreground="#7d0045")
        self.text.tag_configure("attributevalue", foreground="#0000ff")
        self.text.tag_configure("comment", foreground="#808080", font=("Courier", 10, "italic"))
        self.text.tag_configure("xml_declaration", foreground="#800080")
        self.text.tag_configure("error", background="#ffcccb")
        
        # Tags pour complétion
        self.text.tag_configure("completion", background="#eeeeff")
        
        # Liste des balises et attributs WPKG pour autocomplétion
        self.wpkg_tags = ["package", "variable", "check", "install", "upgrade", "remove", "exit"]
        self.wpkg_attributes = {
            "package": ["id", "name", "revision", "date", "reboot", "category", "priority"],
            "variable": ["name", "value", "architecture"],
            "check": ["type", "condition", "path", "value", "architecture"],
            "install": ["cmd", "include", "timeout"],
            "upgrade": ["include", "cmd"],
            "remove": ["cmd", "timeout"],
            "exit": ["code"]
        }
        
        # Bind des événements pour autocomplétion et coloration
        self.text.bind("<KeyRelease>", self.on_key_release)
        self.text.bind("<Tab>", self.handle_tab)
        self.text.bind("<less>", self.on_less_than)
        self.text.bind("<space>", self.on_space)
        
        # Mettre à jour les numéros de ligne quand le contenu change
        self.text.bind("<<Modified>>", self._on_text_modified)
        self.text.bind("<Configure>", self._on_text_configure)
        
        # Initialisation des numéros de ligne
        self._update_line_numbers()
    
    def _on_text_modified(self, event=None):
        self._update_line_numbers()
        self.text.edit_modified(False)
    
    def _on_text_configure(self, event=None):
        self._update_line_numbers()
    
    def _update_line_numbers(self):
        self.linenumbers.delete("all")
        i = self.text.index("@0,0")
        while True:
            dline = self.text.dlineinfo(i)
            if dline is None:
                break
            y = dline[1]
            linenum = str(i).split(".")[0]
            self.linenumbers.create_text(2, y, anchor="nw", text=linenum, font=("Courier", 10))
            i = self.text.index(f"{i}+1line")
    
    def get(self, *args, **kwargs):
        return self.text.get(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        return self.text.delete(*args, **kwargs)
    
    def insert(self, *args, **kwargs):
        return self.text.insert(*args, **kwargs)
    
    def mark_set(self, *args, **kwargs):
        return self.text.mark_set(*args, **kwargs)
    
    def see(self, *args, **kwargs):
        return self.text.see(*args, **kwargs)
    
    def tag_add(self, *args, **kwargs):
        return self.text.tag_add(*args, **kwargs)
    
    def tag_remove(self, *args, **kwargs):
        return self.text.tag_remove(*args, **kwargs)
    
    def clear_highlighting(self):
        for tag in ["tag", "attribute", "attributevalue", "comment", "xml_declaration", "error", "completion"]:
            self.text.tag_remove(tag, "1.0", "end")
    
    def highlight_syntax(self):
        """Applique la coloration syntaxique au code XML"""
        self.clear_highlighting()
        content = self.text.get("1.0", "end-1c")
        
        # Mise en évidence des déclarations XML
        for match in re.finditer(r'<\?xml[^>]*\?>', content):
            start_idx = f"1.0 + {match.start()} chars"
            end_idx = f"1.0 + {match.end()} chars"
            self.text.tag_add("xml_declaration", start_idx, end_idx)
        
        # Mise en évidence des commentaires
        for match in re.finditer(r'<!--(.*?)-->', content, re.DOTALL):
            start_idx = f"1.0 + {match.start()} chars"
            end_idx = f"1.0 + {match.end()} chars"
            self.text.tag_add("comment", start_idx, end_idx)
        
        # Mise en évidence des balises
        for match in re.finditer(r'<[^>]*>', content):
            tag_text = match.group()
            start_idx = f"1.0 + {match.start()} chars"
            end_idx = f"1.0 + {match.end()} chars"
            
            # Highlighting des noms de balises
            tag_match = re.search(r'</?([a-zA-Z0-9_:-]+)', tag_text)
            if tag_match:
                tag_start = match.start() + tag_match.start(1)
                tag_end = match.start() + tag_match.end(1)
                tag_start_idx = f"1.0 + {tag_start} chars"
                tag_end_idx = f"1.0 + {tag_end} chars"
                self.text.tag_add("tag", tag_start_idx, tag_end_idx)
            
            # Highlighting des attributs et leurs valeurs
            for attr_match in re.finditer(r'([a-zA-Z0-9_:-]+)(\s*=\s*)(["\'](.*?)["\'])', tag_text):
                # Nom d'attribut
                attr_start = match.start() + attr_match.start(1)
                attr_end = match.start() + attr_match.end(1)
                attr_start_idx = f"1.0 + {attr_start} chars"
                attr_end_idx = f"1.0 + {attr_end} chars"
                self.text.tag_add("attribute", attr_start_idx, attr_end_idx)
                
                # Valeur d'attribut
                val_start = match.start() + attr_match.start(3)
                val_end = match.start() + attr_match.end(3)
                val_start_idx = f"1.0 + {val_start} chars"
                val_end_idx = f"1.0 + {val_end} chars"
                self.text.tag_add("attributevalue", val_start_idx, val_end_idx)
    
    def highlight_error(self, line_number):
        """Surligne une ligne contenant une erreur"""
        start_idx = f"{line_number}.0"
        end_idx = f"{line_number}.end"
        self.text.tag_add("error", start_idx, end_idx)
        self.text.see(start_idx)  # Faire défiler pour voir l'erreur
    
    def on_key_release(self, event):
        """Mise à jour de la coloration syntaxique lors de la frappe"""
        if event.keysym not in ('Tab', 'less', 'space'):  # Éviter les duplications
            self.highlight_syntax()
    
    def on_less_than(self, event):
        """Gestion de l'autocomplétion lors de la frappe de <"""
        self.text.insert(tk.INSERT, "<")
        return "break"  # Empêche l'insertion du < par défaut
    
    def on_space(self, event):
        """Gestion de l'autocomplétion des attributs après un espace dans une balise"""
        # Obtenir la position actuelle
        pos = self.text.index(tk.INSERT)
        # Vérifier si nous sommes dans une balise
        line = self.text.get(f"{pos} linestart", f"{pos} lineend")
        if "<" in line and ">" not in line[line.rfind("<"):]:
            # Trouver le nom de la balise
            tag_match = re.search(r'<([a-zA-Z0-9_:-]+)', line)
            if tag_match and tag_match.group(1) in self.wpkg_attributes:
                # Insérer un espace normal
                self.text.insert(tk.INSERT, " ")
                return "break"
        # Comportement par défaut
        return None
    
    def handle_tab(self, event):
        """Gestion de l'autocomplétion avec Tab"""
        # Obtenir la position actuelle
        pos = self.text.index(tk.INSERT)
        
        # Vérifier si nous sommes dans une balise ouvrante
        line = self.text.get(f"{pos} linestart", f"{pos} lineend")
        current_pos_in_line = int(pos.split('.')[1])
        
        # Si nous sommes après un <, suggérer des balises
        if "<" in line and ">" not in line[line.rfind("<"):]:
            prefix = line[line.rfind("<")+1:current_pos_in_line]
            
            # Filtrer les balises correspondant au préfixe
            matches = [tag for tag in self.wpkg_tags if tag.startswith(prefix)]
            
            if len(matches) == 1:
                # Une seule correspondance, remplacer directement
                self.text.delete(f"{pos} linestart+{line.rfind('<')+1}c", pos)
                self.text.insert(tk.INSERT, matches[0])
                self.text.insert(tk.INSERT, " ")  # Espace pour attributs
            elif len(matches) > 1:
                # Afficher un menu de suggestions
                self.show_completion_menu(matches, pos, prefix)
        
        # Si nous sommes dans une balise et après un espace, suggérer des attributs
        elif re.search(r'<[a-zA-Z0-9_:-]+\s+[^>]*$', line[:current_pos_in_line]):
            tag_match = re.search(r'<([a-zA-Z0-9_:-]+)', line)
            if tag_match and tag_match.group(1) in self.wpkg_attributes:
                # Trouver le dernier mot (attribut potentiel)
                last_word_match = re.search(r'[a-zA-Z0-9_:-]*$', line[:current_pos_in_line])
                if last_word_match:
                    prefix = last_word_match.group(0)
                    attributes = self.wpkg_attributes[tag_match.group(1)]
                    # Filtrer les attributs correspondant au préfixe
                    matches = [attr for attr in attributes if attr.startswith(prefix)]
                    
                    if len(matches) == 1:
                        # Une seule correspondance, remplacer directement
                        self.text.delete(f"{pos} linestart+{current_pos_in_line-len(prefix)}c", pos)
                        self.text.insert(tk.INSERT, matches[0])
                        self.text.insert(tk.INSERT, '="')  # Préparer pour la valeur
                    elif len(matches) > 1:
                        # Afficher un menu de suggestions
                        self.show_completion_menu(matches, pos, prefix)
        
        return "break"  # Empêche le comportement par défaut de Tab
    
    def show_completion_menu(self, options, pos, prefix):
        """Affiche un menu contextuel avec les options d'autocomplétion"""
        m = tk.Menu(self, tearoff=0)
        
        for option in options:
            m.add_command(
                label=option,
                command=lambda opt=option: self.apply_completion(opt, pos, prefix)
            )
        
        try:
            # Afficher le menu à la position du curseur
            x, y, width, height = self.text.bbox(pos)
            m.post(
                self.text.winfo_rootx() + x,
                self.text.winfo_rooty() + y + height
            )
        except:
            # En cas d'erreur, afficher en position actuelle de la souris
            m.post(self.winfo_pointerx(), self.winfo_pointery())
    
    def apply_completion(self, option, pos, prefix):
        """Applique l'option d'autocomplétion sélectionnée"""
        # Supprimer le préfixe
        current_pos_in_line = int(pos.split('.')[1])
        line = self.text.get(f"{pos} linestart", f"{pos} lineend")
        
        # Déterminer si nous complétons une balise ou un attribut
        if "<" in line and ">" not in line[line.rfind("<"):]:
            if re.search(r'<[a-zA-Z0-9_:-]+\s+[^>]*$', line[:current_pos_in_line]):
                # Complétion d'attribut
                last_word_match = re.search(r'[a-zA-Z0-9_:-]*$', line[:current_pos_in_line])
                if last_word_match:
                    self.text.delete(f"{pos} linestart+{current_pos_in_line-len(prefix)}c", pos)
                    self.text.insert(tk.INSERT, option)
                    self.text.insert(tk.INSERT, '="')  # Préparer pour la valeur
            else:
                # Complétion de balise
                self.text.delete(f"{pos} linestart+{line.rfind('<')+1}c", pos)
                self.text.insert(tk.INSERT, option)
                self.text.insert(tk.INSERT, " ")  # Espace pour attributs


class StatusBar(ttk.Frame):
    """Barre de statut affichant des informations sur l'application"""
    def __init__(self, master):
        super().__init__(master)
        
        # Créer les widgets de la barre de statut
        self.status_label = ttk.Label(self, text="Prêt", anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        # Version et infos système
        system_info = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} | {platform.system()}"
        self.system_label = ttk.Label(self, text=system_info, anchor=tk.E)
        self.system_label.pack(side=tk.RIGHT, padx=5)
        
        # Séparateur
        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, padx=5)
        
        # Position du curseur
        self.cursor_position = ttk.Label(self, text="Ligne: 1, Col: 1", width=20, anchor=tk.E)
        self.cursor_position.pack(side=tk.RIGHT, padx=5)
    
    def set_status(self, message):
        """Met à jour le message de statut"""
        self.status_label.config(text=message)
    
    def update_cursor_position(self, line, column):
        """Met à jour l'information sur la position du curseur"""
        self.cursor_position.config(text=f"Ligne: {line}, Col: {column}")


class SearchReplaceDialog(tk.Toplevel):
    """Dialogue de recherche et remplacement pour l'éditeur XML"""
    def __init__(self, parent, text_widget):
        super().__init__(parent)
        self.title("Rechercher et remplacer")
        self.transient(parent)
        self.resizable(False, False)
        
        self.parent = parent
        self.text_widget = text_widget
        self.result = None
        
        # Variables
        self.search_var = tk.StringVar()
        self.replace_var = tk.StringVar()
        self.case_sensitive = tk.BooleanVar(value=False)
        self.whole_word = tk.BooleanVar(value=False)
        self.regex_search = tk.BooleanVar(value=False)
        
        # Position de recherche courante
        self.current_pos = "1.0"
        
        # Construction du dialogue
        self.create_widgets()
        
        # Centrer la fenêtre
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (parent.winfo_width() - width) // 2 + parent.winfo_x()
        y = (parent.winfo_height() - height) // 2 + parent.winfo_y()
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        # Passer le focus à la zone de recherche
        self.search_entry.focus_set()
        
        # Rendre la fenêtre modale
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda event: self.cancel())
        
    def create_widgets(self):
        frame = ttk.Frame(self, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Champ de recherche
        ttk.Label(frame, text="Rechercher:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.search_entry = ttk.Entry(frame, textvariable=self.search_var, width=30)
        self.search_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        
        # Champ de remplacement
        ttk.Label(frame, text="Remplacer par:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.replace_entry = ttk.Entry(frame, textvariable=self.replace_var, width=30)
        self.replace_entry.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        
        # Options de recherche
        options_frame = ttk.LabelFrame(frame, text="Options")
        options_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=10)
        
        ttk.Checkbutton(options_frame, text="Respecter la casse", variable=self.case_sensitive).pack(anchor=tk.W, padx=5, pady=2)
        ttk.Checkbutton(options_frame, text="Mot entier", variable=self.whole_word).pack(anchor=tk.W, padx=5, pady=2)
        ttk.Checkbutton(options_frame, text="Expression régulière", variable=self.regex_search).pack(anchor=tk.W, padx=5, pady=2)
        
        # Boutons
        buttons_frame = ttk.Frame(frame)
        buttons_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        ttk.Button(buttons_frame, text="Rechercher", command=self.find_next).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Remplacer", command=self.replace).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Remplacer tout", command=self.replace_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Fermer", command=self.cancel).pack(side=tk.LEFT, padx=5)
        
        # Configuration de la grille
        frame.columnconfigure(1, weight=1)
    
    def find_next(self, start_pos=None):
        """Trouve la prochaine occurrence du texte recherché"""
        if start_pos is None:
            start_pos = self.current_pos
        
        search_text = self.search_var.get()
        if not search_text:
            return False
        
        # Options de recherche
        kwargs = {}
        if not self.case_sensitive.get():
            kwargs["nocase"] = True
        if self.regex_search.get():
            kwargs["regexp"] = True
        if self.whole_word.get():
            kwargs["regexp"] = True
            search_text = f"\\y{search_text}\\y"
        
        # Supprimer le tag 'found' précédent
        self.text_widget.text.tag_remove("found", "1.0", tk.END)
        self.text_widget.text.tag_configure("found", background="yellow")
        
        # Rechercher
        try:
            pos = self.text_widget.text.search(search_text, start_pos, tk.END, **kwargs)
            if not pos:
                # Rechercher depuis le début si on atteint la fin
                if start_pos != "1.0":
                    self.parent.status_bar.set_status("Recherche depuis le début...")
                    return self.find_next("1.0")
                else:
                    self.parent.status_bar.set_status(f"Aucune occurrence de '{search_text}' trouvée.")
                    return False
            
            # Calculer la fin de la correspondance
            line, char = pos.split('.')
            end_pos = f"{line}.{int(char) + len(search_text)}"
            if "regexp" in kwargs:
                # Pour les regex, il faut utiliser tag_add
                end_pos = self.text_widget.text.index(f"{pos}+{len(self.text_widget.text.get(pos, pos+'+1c'))}c")
            
            # Mettre en évidence la correspondance
            self.text_widget.text.tag_add("found", pos, end_pos)
            self.text_widget.see(pos)
            
            # Mettre à jour la position courante pour la prochaine recherche
            self.current_pos = end_pos
            
            self.parent.status_bar.set_status(f"Occurrence trouvée.")
            return True
        except Exception as e:
            self.parent.status_bar.set_status(f"Erreur lors de la recherche: {str(e)}")
            return False
    
    def replace(self):
        """Remplace l'occurrence actuelle du texte recherché"""
        search_text = self.search_var.get()
        replace_text = self.replace_var.get()
        
        if not search_text:
            return
        
        # Si une occurrence est déjà trouvée (tag 'found')
        if self.text_widget.text.tag_ranges("found"):
            start, end = self.text_widget.text.tag_ranges("found")[0], self.text_widget.text.tag_ranges("found")[1]
            self.text_widget.text.delete(start, end)
            self.text_widget.text.insert(start, replace_text)
            self.text_widget.text.tag_remove("found", "1.0", tk.END)
            
            # Position après le texte de remplacement
            self.current_pos = f"{start}+{len(replace_text)}c"
            
            # Chercher l'occurrence suivante
            self.find_next()
        else:
            # Chercher d'abord une occurrence
            self.find_next()
    
    def replace_all(self):
        """Remplace toutes les occurrences du texte recherché"""
        search_text = self.search_var.get()
        replace_text = self.replace_var.get()
        
        if not search_text:
            return
        
        # Sauvegarder la position actuelle
        current_view = self.text_widget.text.yview()
        
        # Commencer depuis le début
        self.current_pos = "1.0"
        count = 0
        
        # Utiliser un indicateur pour terminer la boucle
        text_modified = False
        
        while True:
            if self.find_next("1.0" if count == 0 else self.current_pos):
                if self.text_widget.text.tag_ranges("found"):
                    start, end = self.text_widget.text.tag_ranges("found")[0], self.text_widget.text.tag_ranges("found")[1]
                    self.text_widget.text.delete(start, end)
                    self.text_widget.text.insert(start, replace_text)
                    self.text_widget.text.tag_remove("found", "1.0", tk.END)
                    
                    # Position après le texte de remplacement
                    self.current_pos = f"{start}+{len(replace_text)}c"
                    count += 1
                    text_modified = True
                else:
                    break
            else:
                break
        
        # Restaurer la vue
        self.text_widget.text.yview_moveto(current_view[0])
        
        if text_modified:
            # Si des remplacements ont été effectués, mettre à jour la coloration syntaxique
            self.text_widget.highlight_syntax()
        
        self.parent.status_bar.set_status(f"{count} occurrences remplacées.")
    
    def cancel(self):
        """Ferme le dialogue"""
        self.text_widget.text.tag_remove("found", "1.0", tk.END)
        self.destroy()


class EditorTheme:
    """Gestionnaire de thèmes pour l'éditeur"""
    
    THEMES = {
        "clair": {
            "background": "#ffffff",
            "foreground": "#000000",
            "xml_tag": "#008000",
            "xml_attribute": "#7d0045",
            "xml_value": "#0000ff",
            "xml_comment": "#808080",
            "xml_declaration": "#800080",
            "error": "#ffcccb",
            "found": "#ffff00",
            "selection": "#add8e6"
        },
        "sombre": {
            "background": "#2d2d2d",
            "foreground": "#d4d4d4",
            "xml_tag": "#4ec9b0",
            "xml_attribute": "#9cdcfe",
            "xml_value": "#ce9178",
            "xml_comment": "#6a9955",
            "xml_declaration": "#808080",
            "error": "#5c0000",
            "found": "#515c00",
            "selection": "#264f78"
        },
        "haute_visibilité": {
            "background": "#000000",
            "foreground": "#ffffff",
            "xml_tag": "#00ff00",
            "xml_attribute": "#ff00ff",
            "xml_value": "#ffff00",
            "xml_comment": "#808080",
            "xml_declaration": "#c0c0c0",
            "error": "#ff0000",
            "found": "#00ff00",
            "selection": "#0000ff"
        }
    }
    
    @classmethod
    def apply_theme(cls, root, theme_name, xml_widget, log_widget):
        """Applique un thème à l'application"""
        if theme_name not in cls.THEMES:
            theme_name = "clair"  # Thème par défaut
        
        theme = cls.THEMES[theme_name]
        
        # Style de l'application
        style = ttk.Style(root)
        
        if theme_name == "clair":
            style.theme_use("clam")
        elif theme_name == "sombre":
            style.theme_use("alt")
        elif theme_name == "haute_visibilité":
            style.theme_use("classic")
        
        # Configurer les couleurs des widgets Tkinter
        xml_widget.text.configure(
            background=theme["background"],
            foreground=theme["foreground"],
            insertbackground=theme["foreground"],
            selectbackground=theme["selection"]
        )
        
        log_widget.configure(
            background=theme["background"],
            foreground=theme["foreground"],
            insertbackground=theme["foreground"],
            selectbackground=theme["selection"]
        )
        
        # Configurer les tags XML
        xml_widget.text.tag_configure("tag", foreground=theme["xml_tag"])
        xml_widget.text.tag_configure("attribute", foreground=theme["xml_attribute"])
        xml_widget.text.tag_configure("attributevalue", foreground=theme["xml_value"])
        xml_widget.text.tag_configure("comment", foreground=theme["xml_comment"])
        xml_widget.text.tag_configure("xml_declaration", foreground=theme["xml_declaration"])
        xml_widget.text.tag_configure("error", background=theme["error"])
        xml_widget.text.tag_configure("found", background=theme["found"])
        
        # Configurer les tags du log
        log_widget.tag_configure("error", foreground="#ff0000")
        log_widget.tag_configure("warning", foreground="#ff8c00")
        log_widget.tag_configure("info", foreground="#0000ff")
        log_widget.tag_configure("success", foreground="#008000")
        log_widget.tag_configure("cmd", foreground="#800080")
        
        return theme


class WPKGEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("WPKG Package Editor v1.2")
        self.root.geometry("1300x900")
        
        # Variables pour le paquet en cours d'édition
        self.current_file = None
        
        # Utilisation de la nouvelle classe Package
        self.package = Package()
        
        # Variables pour contrôler l'affichage des panneaux
        self.show_xml_panel = tk.BooleanVar(value=True)
        self.show_log_panel = tk.BooleanVar(value=True)
        
        # Variable pour le thème actuel
        self.current_theme = tk.StringVar(value="clair")
        
        # Liste des fichiers récents
        self.recent_files = []
        self.max_recent_files = 5
        self.load_recent_files()
        
        # Paramètres utilisateur
        self.user_settings = {
            "theme": "clair",
            "autosave": False,
            "autosave_interval": 5,  # minutes
            "xml_font_size": 10,
            "log_font_size": 10
        }
        self.load_settings()
        
        # Timer pour sauvegarde automatique
        self.autosave_timer = None
        
        # Historique des actions pour annuler/refaire
        self.history = []
        self.history_position = -1
        self.max_history = 50
        
        # Configuration de la fenêtre
        self.setup_ui()
        self.apply_settings()
        
        # Démarrer la sauvegarde automatique si activée
        if self.user_settings["autosave"]:
            self.start_autosave_timer()
    
    def setup_ui(self):
        # Menu principal
        menubar = tk.Menu(self.root)
        
        # Menu Fichier
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Nouveau Paquet", command=self.new_package, accelerator="Ctrl+N")
        file_menu.add_command(label="Ouvrir Paquet", command=self.open_package, accelerator="Ctrl+O")
        
        # Sous-menu Fichiers Récents
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        self.update_recent_files_menu()
        file_menu.add_cascade(label="Fichiers Récents", menu=self.recent_menu)
        
        file_menu.add_separator()
        file_menu.add_command(label="Enregistrer", command=self.save_package, accelerator="Ctrl+S")
        file_menu.add_command(label="Enregistrer sous...", command=self.save_package_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Exporter en HTML", command=self.export_to_html)
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self.on_close, accelerator="Alt+F4")
        
        # Menu Édition
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Annuler", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Refaire", command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Couper", command=lambda: self.root.focus_get().event_generate("<<Cut>>"), accelerator="Ctrl+X")
        edit_menu.add_command(label="Copier", command=lambda: self.root.focus_get().event_generate("<<Copy>>"), accelerator="Ctrl+C")
        edit_menu.add_command(label="Coller", command=lambda: self.root.focus_get().event_generate("<<Paste>>"), accelerator="Ctrl+V")
        edit_menu.add_separator()
        edit_menu.add_command(label="Rechercher/Remplacer", command=self.show_search_dialog, accelerator="Ctrl+F")
        
        # Menu Affichage
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label="Afficher Panneau XML", variable=self.show_xml_panel, 
                                 command=self.toggle_xml_panel)
        view_menu.add_checkbutton(label="Afficher Panneau LOG", variable=self.show_log_panel, 
                                 command=self.toggle_log_panel)
        
        # Sous-menu Thèmes
        themes_menu = tk.Menu(view_menu, tearoff=0)
        for theme_name in EditorTheme.THEMES.keys():
            themes_menu.add_radiobutton(
                label=theme_name.capitalize(), 
                variable=self.current_theme,
                value=theme_name,
                command=lambda: self.change_theme(self.current_theme.get())
            )
        view_menu.add_cascade(label="Thèmes", menu=themes_menu)
        
        # Zoom du texte
        view_menu.add_command(label="Zoom +", command=lambda: self.change_font_size(1), accelerator="Ctrl++")
        view_menu.add_command(label="Zoom -", command=lambda: self.change_font_size(-1), accelerator="Ctrl+-")
        view_menu.add_command(label="Taille par défaut", command=lambda: self.reset_font_size(), accelerator="Ctrl+0")
        
        # Menu Outils
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Vérifier XML", command=self.verify_xml, accelerator="F7")
        tools_menu.add_command(label="Formater XML", command=self.format_xml, accelerator="F8")
        tools_menu.add_separator()
        tools_menu.add_command(label="Générer paquet modèle", command=self.generate_template)
        tools_menu.add_command(label="Comparer avec un autre paquet", command=self.compare_packages)
        tools_menu.add_separator()
        tools_menu.add_command(label="Paramètres", command=self.show_settings_dialog)
        
        # Menu Aide
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Documentation", command=self.show_documentation)
        help_menu.add_command(label="Raccourcis clavier", command=self.show_keyboard_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="Vérifier les mises à jour", command=self.check_updates)
        help_menu.add_command(label="À propos", command=self.show_about)
        
        menubar.add_cascade(label="Fichier", menu=file_menu)
        menubar.add_cascade(label="Édition", menu=edit_menu)
        menubar.add_cascade(label="Affichage", menu=view_menu)
        menubar.add_cascade(label="Outils", menu=tools_menu)
        menubar.add_cascade(label="Aide", menu=help_menu)
        
        self.root.config(menu=menubar)
        
        # Frame principal
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Configuration des panneaux
        self.setup_panels()
        
        # Barre de statut
        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Raccourcis clavier
        self.setup_keyboard_shortcuts()
    
    def setup_panels(self):
        # Paned Window pour diviser l'interface en trois parties
        self.top_paned = ttk.PanedWindow(self.main_frame, orient=tk.VERTICAL)
        self.top_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Partie supérieure: formulaire d'édition
        self.form_frame = ttk.Frame(self.top_paned)
        self.top_paned.add(self.form_frame, weight=2)
        
        # Partie inférieure: code XML et logs
        self.bottom_frame = ttk.Frame(self.top_paned)
        self.top_paned.add(self.bottom_frame, weight=1)
        
        # Paned Window pour diviser la partie inférieure en code XML et logs
        self.bottom_paned = ttk.PanedWindow(self.bottom_frame, orient=tk.VERTICAL)
        self.bottom_paned.pack(fill=tk.BOTH, expand=True)
        
        # Configuration du formulaire d'édition (avec onglets)
        self.setup_form()
        
        # Configuration de l'affichage XML et LOG
        self.setup_xml_view()
        self.setup_log_view()
        
        # Sélection de caractères spéciaux
        self.setup_special_chars()
        
        # Bouton de vérification XML
        self.verify_button = ttk.Button(self.bottom_frame, text="Vérifier l'intégrité XML", 
                                       command=self.verify_xml)
        self.verify_button.pack(side=tk.TOP, pady=5)
    
    def setup_form(self):
        # Notebook pour les onglets du formulaire
        self.form_notebook = ttk.Notebook(self.form_frame)
        self.form_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Onglet Général (attributs principaux du paquet)
        self.general_frame = ttk.Frame(self.form_notebook)
        self.form_notebook.add(self.general_frame, text="Général")
        
        # Onglet Variables
        self.variables_frame = ttk.Frame(self.form_notebook)
        self.form_notebook.add(self.variables_frame, text="Variables")
        
        # Onglet Checks
        self.checks_frame = ttk.Frame(self.form_notebook)
        self.form_notebook.add(self.checks_frame, text="Checks")
        
        # Onglet Install
        self.installs_frame = ttk.Frame(self.form_notebook)
        self.form_notebook.add(self.installs_frame, text="Install")
        
        # Onglet Upgrade
        self.upgrades_frame = ttk.Frame(self.form_notebook)
        self.form_notebook.add(self.upgrades_frame, text="Upgrade")
        
        # Onglet Remove
        self.removes_frame = ttk.Frame(self.form_notebook)
        self.form_notebook.add(self.removes_frame, text="Remove")
        
        # Onglet Commentaires
        self.comments_frame = ttk.Frame(self.form_notebook)
        self.form_notebook.add(self.comments_frame, text="Commentaires")
        
        # Configuration de chaque onglet
        self.setup_general_tab()
        self.setup_variables_tab()
        self.setup_checks_tab()
        self.setup_installs_tab()
        self.setup_upgrades_tab()
        self.setup_removes_tab()
        self.setup_comments_tab()
    
    def setup_general_tab(self):
        # Formulaire pour les attributs du paquet
        form_frame = ttk.LabelFrame(self.general_frame, text="Attributs du paquet")
        form_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Création des champs pour chaque attribut
        self.package_vars = {}
        
        row = 0
        for key in asdict(self.package).keys():
            if key in ["variables", "checks", "installs", "upgrades", "removes", "comments", "xml_declaration"]:
                continue
                
            ttk.Label(form_frame, text=f"{key.capitalize()}:").grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
            
            if key == 'reboot':
                self.package_vars[key] = tk.StringVar(value=getattr(self.package, key))
                combo = ttk.Combobox(form_frame, textvariable=self.package_vars[key], values=('true', 'false'))
                combo.grid(row=row, column=1, sticky=tk.W, padx=5, pady=5)
            else:
                self.package_vars[key] = tk.StringVar(value=getattr(self.package, key))
                entry = ttk.Entry(form_frame, textvariable=self.package_vars[key], width=40)
                entry.grid(row=row, column=1, sticky=tk.W, padx=5, pady=5)
            
            row += 1
        
        # Bouton pour générer une date actuelle
        ttk.Button(form_frame, text="Date actuelle", 
                 command=self.set_current_date).grid(row=3, column=2, padx=5, pady=5)
        
        # Bouton pour mettre à jour le code XML
        ttk.Button(form_frame, text="Mettre à jour XML", 
                 command=self.update_xml).grid(row=row, column=0, columnspan=2, pady=10)
    
    def setup_variables_tab(self):
        # Frame principale
        main_frame = ttk.Frame(self.variables_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Liste des variables
        list_frame = ttk.LabelFrame(main_frame, text="Liste des variables")
        list_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=5, pady=5)
        
        # Treeview pour afficher les variables
        self.variables_tree = ttk.Treeview(list_frame, columns=('name', 'value', 'architecture'), show='headings')
        self.variables_tree.heading('name', text='Nom')
        self.variables_tree.heading('value', text='Valeur')
        self.variables_tree.heading('architecture', text='Architecture')
        self.variables_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbars
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.variables_tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.variables_tree.xview)
        self.variables_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Frame d'édition de variable
        edit_frame = ttk.LabelFrame(main_frame, text="Éditer variable")
        edit_frame.pack(fill=tk.BOTH, expand=True, side=tk.RIGHT, padx=5, pady=5)
        
        # Champs d'édition
        ttk.Label(edit_frame, text="Nom:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.var_name = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.var_name, width=30).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Valeur:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.var_value = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.var_value, width=30).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Architecture:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.var_arch = tk.StringVar()
        ttk.Combobox(edit_frame, textvariable=self.var_arch, 
                    values=('', 'x86', 'x64')).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Boutons
        buttons_frame = ttk.Frame(edit_frame)
        buttons_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        ttk.Button(buttons_frame, text="Ajouter", command=self.add_variable).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Mettre à jour", command=self.update_variable).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Supprimer", command=self.delete_variable).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Dupliquer", command=self.duplicate_variable).pack(side=tk.LEFT, padx=5)
        
        # Événement de sélection
        self.variables_tree.bind('<<TreeviewSelect>>', self.on_variable_select)
    
    def setup_checks_tab(self):
        # Frame principale
        main_frame = ttk.Frame(self.checks_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Liste des checks
        list_frame = ttk.LabelFrame(main_frame, text="Liste des vérifications")
        list_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=5, pady=5)
        
        # Treeview pour afficher les checks
        self.checks_tree = ttk.Treeview(list_frame, columns=('type', 'condition', 'path', 'value', 'architecture'), show='headings')
        self.checks_tree.heading('type', text='Type')
        self.checks_tree.heading('condition', text='Condition')
        self.checks_tree.heading('path', text='Chemin')
        self.checks_tree.heading('value', text='Valeur')
        self.checks_tree.heading('architecture', text='Architecture')
        self.checks_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbars
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.checks_tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.checks_tree.xview)
        self.checks_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Frame d'édition de check
        edit_frame = ttk.LabelFrame(main_frame, text="Éditer vérification")
        edit_frame.pack(fill=tk.BOTH, expand=True, side=tk.RIGHT, padx=5, pady=5)
        
        # Champs d'édition
        ttk.Label(edit_frame, text="Type:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.check_type = tk.StringVar()
        ttk.Combobox(edit_frame, textvariable=self.check_type, 
                    values=('file', 'uninstall', 'registry')).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Condition:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.check_condition = tk.StringVar()
        ttk.Combobox(edit_frame, textvariable=self.check_condition, 
                    values=('exists', 'versionequalto', 'versiongreaterequalto')).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Chemin:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.check_path = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.check_path, width=30).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Valeur:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.check_value = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.check_value, width=30).grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Architecture:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.check_arch = tk.StringVar()
        ttk.Combobox(edit_frame, textvariable=self.check_arch, 
                    values=('', 'x86', 'x64')).grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Boutons
        buttons_frame = ttk.Frame(edit_frame)
        buttons_frame.grid(row=5, column=0, columnspan=2, pady=10)
        
        ttk.Button(buttons_frame, text="Ajouter", command=self.add_check).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Mettre à jour", command=self.update_check).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Supprimer", command=self.delete_check).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Dupliquer", command=self.duplicate_check).pack(side=tk.LEFT, padx=5)
        
        # Événement de sélection
        self.checks_tree.bind('<<TreeviewSelect>>', self.on_check_select)
    
    def setup_installs_tab(self):
        # Frame principale
        main_frame = ttk.Frame(self.installs_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Liste des commandes d'installation
        list_frame = ttk.LabelFrame(main_frame, text="Commandes d'installation")
        list_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=5, pady=5)
        
        # Treeview pour afficher les commandes
        self.installs_tree = ttk.Treeview(list_frame, columns=('cmd', 'include', 'timeout'), show='headings')
        self.installs_tree.heading('cmd', text='Commande')
        self.installs_tree.heading('include', text='Include')
        self.installs_tree.heading('timeout', text='Timeout')
        self.installs_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbars
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.installs_tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.installs_tree.xview)
        self.installs_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Frame d'édition de commande
        edit_frame = ttk.LabelFrame(main_frame, text="Éditer commande")
        edit_frame.pack(fill=tk.BOTH, expand=True, side=tk.RIGHT, padx=5, pady=5)
        
        # Champs d'édition
        ttk.Label(edit_frame, text="Commande:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.install_cmd = tk.StringVar()
        self.install_cmd_entry = ttk.Entry(edit_frame, textvariable=self.install_cmd, width=40)
        self.install_cmd_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Bouton pour caractères spéciaux
        ttk.Button(edit_frame, text="Caractères XML", 
                 command=lambda: self.show_special_chars_dialog(self.install_cmd_entry)).grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Include:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.install_include = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.install_include, width=30).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Timeout:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.install_timeout = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.install_timeout, width=10).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Exit Code:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.install_exit_code = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.install_exit_code, width=10).grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Boutons
        buttons_frame = ttk.Frame(edit_frame)
        buttons_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        ttk.Button(buttons_frame, text="Ajouter", command=self.add_install).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Mettre à jour", command=self.update_install).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Supprimer", command=self.delete_install).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Dupliquer", command=self.duplicate_install).pack(side=tk.LEFT, padx=5)
        
        # Boutons pour construire et exécuter la commande
        cmd_buttons_frame = ttk.Frame(edit_frame)
        cmd_buttons_frame.grid(row=5, column=0, columnspan=3, pady=10)
        
        ttk.Button(cmd_buttons_frame, text="Construire Commande", 
                 command=self.build_install_command).pack(side=tk.LEFT, padx=5)
        
        # Bouton exécuter seulement sous Windows
        if platform.system() == "Windows":
            ttk.Button(cmd_buttons_frame, text="Exécuter Commande", 
                     command=self.execute_install_command).pack(side=tk.LEFT, padx=5)
        
        # Drag and drop des commandes (réorganisation)
        self.installs_tree.bind("<ButtonPress-1>", self.on_tree_button_press)
        self.installs_tree.bind("<B1-Motion>", self.on_tree_motion)
        self.installs_tree.bind("<ButtonRelease-1>", self.on_tree_button_release)
        
        # Événement de sélection
        self.installs_tree.bind('<<TreeviewSelect>>', self.on_install_select)
    
    def setup_upgrades_tab(self):
        # Frame principale
        main_frame = ttk.Frame(self.upgrades_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Liste des commandes de mise à niveau
        list_frame = ttk.LabelFrame(main_frame, text="Commandes de mise à niveau")
        list_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=5, pady=5)
        
        # Treeview pour afficher les commandes
        self.upgrades_tree = ttk.Treeview(list_frame, columns=('include', 'cmd'), show='headings')
        self.upgrades_tree.heading('include', text='Include')
        self.upgrades_tree.heading('cmd', text='Commande')
        self.upgrades_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbars
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.upgrades_tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.upgrades_tree.xview)
        self.upgrades_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Frame d'édition de commande
        edit_frame = ttk.LabelFrame(main_frame, text="Éditer commande")
        edit_frame.pack(fill=tk.BOTH, expand=True, side=tk.RIGHT, padx=5, pady=5)
        
        # Champs d'édition
        ttk.Label(edit_frame, text="Include:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.upgrade_include = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.upgrade_include, width=30).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Commande:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.upgrade_cmd = tk.StringVar()
        self.upgrade_cmd_entry = ttk.Entry(edit_frame, textvariable=self.upgrade_cmd, width=40)
        self.upgrade_cmd_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Bouton pour caractères spéciaux
        ttk.Button(edit_frame, text="Caractères XML", 
                 command=lambda: self.show_special_chars_dialog(self.upgrade_cmd_entry)).grid(row=1, column=2, padx=5, pady=5)
        
        # Boutons
        buttons_frame = ttk.Frame(edit_frame)
        buttons_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        ttk.Button(buttons_frame, text="Ajouter", command=self.add_upgrade).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Mettre à jour", command=self.update_upgrade).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Supprimer", command=self.delete_upgrade).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Dupliquer", command=self.duplicate_upgrade).pack(side=tk.LEFT, padx=5)
        
        # Boutons pour construire et exécuter la commande
        cmd_buttons_frame = ttk.Frame(edit_frame)
        cmd_buttons_frame.grid(row=3, column=0, columnspan=3, pady=10)
        
        ttk.Button(cmd_buttons_frame, text="Construire Commande", 
                 command=self.build_upgrade_command).pack(side=tk.LEFT, padx=5)
        
        # Bouton exécuter seulement sous Windows
        if platform.system() == "Windows":
            ttk.Button(cmd_buttons_frame, text="Exécuter Commande", 
                     command=self.execute_upgrade_command).pack(side=tk.LEFT, padx=5)
        
        # Événement de sélection
        self.upgrades_tree.bind('<<TreeviewSelect>>', self.on_upgrade_select)
    
    def setup_removes_tab(self):
        # Frame principale
        main_frame = ttk.Frame(self.removes_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Liste des commandes de suppression
        list_frame = ttk.LabelFrame(main_frame, text="Commandes de suppression")
        list_frame.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=5, pady=5)
        
        # Treeview pour afficher les commandes
        self.removes_tree = ttk.Treeview(list_frame, columns=('cmd', 'timeout'), show='headings')
        self.removes_tree.heading('cmd', text='Commande')
        self.removes_tree.heading('timeout', text='Timeout')
        self.removes_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbars
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.removes_tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.removes_tree.xview)
        self.removes_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Frame d'édition de commande
        edit_frame = ttk.LabelFrame(main_frame, text="Éditer commande")
        edit_frame.pack(fill=tk.BOTH, expand=True, side=tk.RIGHT, padx=5, pady=5)
        
        # Champs d'édition
        ttk.Label(edit_frame, text="Commande:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.remove_cmd = tk.StringVar()
        self.remove_cmd_entry = ttk.Entry(edit_frame, textvariable=self.remove_cmd, width=40)
        self.remove_cmd_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Bouton pour caractères spéciaux
        ttk.Button(edit_frame, text="Caractères XML", 
                 command=lambda: self.show_special_chars_dialog(self.remove_cmd_entry)).grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Timeout:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.remove_timeout = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.remove_timeout, width=10).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(edit_frame, text="Exit Code:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.remove_exit_code = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.remove_exit_code, width=10).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Boutons
        buttons_frame = ttk.Frame(edit_frame)
        buttons_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        ttk.Button(buttons_frame, text="Ajouter", command=self.add_remove).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Mettre à jour", command=self.update_remove).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Supprimer", command=self.delete_remove).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Dupliquer", command=self.duplicate_remove).pack(side=tk.LEFT, padx=5)
        
        # Boutons pour construire et exécuter la commande
        cmd_buttons_frame = ttk.Frame(edit_frame)
        cmd_buttons_frame.grid(row=4, column=0, columnspan=3, pady=10)
        
        ttk.Button(cmd_buttons_frame, text="Construire Commande", 
                 command=self.build_remove_command).pack(side=tk.LEFT, padx=5)
        
        # Bouton exécuter seulement sous Windows
        if platform.system() == "Windows":
            ttk.Button(cmd_buttons_frame, text="Exécuter Commande", 
                     command=self.execute_remove_command).pack(side=tk.LEFT, padx=5)
        
        # Événement de sélection
        self.removes_tree.bind('<<TreeviewSelect>>', self.on_remove_select)
    
    def setup_comments_tab(self):
        # Frame principale
        main_frame = ttk.Frame(self.comments_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Zone de texte pour les commentaires
        ttk.Label(main_frame, text="Commentaires du paquet:").pack(anchor=tk.W, padx=5, pady=5)
        
        self.comments_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=80, height=20)
        self.comments_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Bouton pour mettre à jour les commentaires
        ttk.Button(main_frame, text="Mettre à jour commentaires", command=self.update_comments).pack(pady=10)
    
    def setup_xml_view(self):
        # Frame pour l'affichage XML
        self.xml_frame = ttk.LabelFrame(self.bottom_paned, text="Code XML")
        self.bottom_paned.add(self.xml_frame, weight=1)
        
        # Zone de texte avancée pour le code XML avec numéros de ligne et coloration syntaxique
        self.xml_text = XmlTextWithLineNumbers(self.xml_frame, width=80, height=15)
        self.xml_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Observer le curseur pour la barre de statut
        self.xml_text.text.bind("<KeyRelease>", self.update_cursor_position_from_text)
        self.xml_text.text.bind("<ButtonRelease-1>", self.update_cursor_position_from_text)
        
        # Boutons pour les actions XML
        buttons_frame = ttk.Frame(self.xml_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(buttons_frame, text="Mettre à jour depuis XML", command=self.update_from_xml).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Formater XML", command=self.format_xml).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Rechercher/Remplacer", command=self.show_search_dialog).pack(side=tk.LEFT, padx=5)
    
    def setup_log_view(self):
        # Frame pour l'affichage des logs
        self.log_frame = ttk.LabelFrame(self.bottom_paned, text="Log")
        self.bottom_paned.add(self.log_frame, weight=1)
        
        # Zone de texte pour les logs
        self.log_text = scrolledtext.ScrolledText(self.log_frame, wrap=tk.WORD, width=80, height=5)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Configuration des tags pour coloration des logs
        self.log_text.tag_configure("error", foreground="red")
        self.log_text.tag_configure("warning", foreground="orange")
        self.log_text.tag_configure("info", foreground="blue")
        self.log_text.tag_configure("success", foreground="green")
        self.log_text.tag_configure("cmd", foreground="purple")
        
        # Bouton pour effacer les logs
        buttons_frame = ttk.Frame(self.log_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(buttons_frame, text="Effacer les logs", command=self.clear_logs).pack(side=tk.LEFT, pady=5)
        ttk.Button(buttons_frame, text="Exporter les logs", command=self.export_logs).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(buttons_frame, text="Charger les logs", command=self.load_logs).pack(side=tk.LEFT, padx=5, pady=5)
    
    def setup_special_chars(self):
        # Frame pour les caractères spéciaux
        special_frame = ttk.LabelFrame(self.xml_frame, text="Caractères spéciaux")
        special_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Liste des caractères spéciaux courants en XML
        special_chars = [
            ('&amp;', '&'), 
            ('&lt;', '<'), 
            ('&gt;', '>'), 
            ('&quot;', '"'), 
            ('&apos;', "'"),
            ('&#xA;', 'Nouvelle ligne'),
            ('&#xD;', 'Retour chariot'),
            ('&#x9;', 'Tabulation')
        ]
        
        # Création des boutons pour insérer les caractères spéciaux
        for i, (char, desc) in enumerate(special_chars):
            ttk.Button(special_frame, text=f"{desc} ({char})", 
                      command=lambda c=char: self.insert_special_char(c)).pack(side=tk.LEFT, padx=5, pady=5)
    
    def setup_keyboard_shortcuts(self):
        # Raccourcis pour le menu Fichier
        self.root.bind("<Control-n>", lambda event: self.new_package())
        self.root.bind("<Control-o>", lambda event: self.open_package())
        self.root.bind("<Control-s>", lambda event: self.save_package())
        self.root.bind("<Control-Shift-s>", lambda event: self.save_package_as())
        
        # Raccourcis pour le menu Édition
        self.root.bind("<Control-z>", lambda event: self.undo())
        self.root.bind("<Control-y>", lambda event: self.redo())
        self.root.bind("<Control-f>", lambda event: self.show_search_dialog())
        
        # Raccourcis pour le menu Affichage
        self.root.bind("<Control-plus>", lambda event: self.change_font_size(1))
        self.root.bind("<Control-minus>", lambda event: self.change_font_size(-1))
        self.root.bind("<Control-0>", lambda event: self.reset_font_size())
        
        # Raccourcis pour le menu Outils
        self.root.bind("<F7>", lambda event: self.verify_xml())
        self.root.bind("<F8>", lambda event: self.format_xml())
    
    def show_special_chars_dialog(self, entry_widget):
        """Affiche une boîte de dialogue pour insérer des caractères spéciaux dans un champ de texte"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Caractères spéciaux XML")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Liste des caractères spéciaux courants en XML
        special_chars = [
            ('&amp;', '& (esperluette)'), 
            ('&lt;', '< (inférieur)'), 
            ('&gt;', '> (supérieur)'), 
            ('&quot;', '" (guillemet)'), 
            ('&apos;', "' (apostrophe)"),
            ('&#xA;', 'Nouvelle ligne'),
            ('&#xD;', 'Retour chariot'),
            ('&#x9;', 'Tabulation')
        ]
        
        # Création des boutons pour insérer les caractères spéciaux
        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        row, col = 0, 0
        for char, desc in special_chars:
            ttk.Button(frame, text=desc, width=15,
                      command=lambda c=char, e=entry_widget: self.insert_special_char_to_entry(c, e, dialog)).grid(
                row=row, column=col, padx=5, pady=5)
            col += 1
            if col > 2:
                col = 0
                row += 1
        
        ttk.Button(dialog, text="Fermer", command=dialog.destroy).pack(pady=10)
    
    def insert_special_char_to_entry(self, char, entry_widget, dialog=None):
        """Insère un caractère spécial dans un widget d'entrée à la position du curseur"""
        try:
            current_text = entry_widget.get()
            current_pos = entry_widget.index(tk.INSERT)
            new_text = current_text[:current_pos] + char + current_text[current_pos:]
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, new_text)
            entry_widget.icursor(current_pos + len(char))  # Déplacer le curseur après le caractère inséré
            
            # Focus sur l'entrée
            entry_widget.focus_set()
            
            if dialog:
                dialog.destroy()
        except Exception as e:
            self.log_message(f"Erreur lors de l'insertion du caractère: {str(e)}", "error")
    
    def toggle_xml_panel(self):
        """Affiche ou masque le panneau XML"""
        if self.show_xml_panel.get():
            self.bottom_paned.add(self.xml_frame, weight=1)
        else:
            self.bottom_paned.remove(self.xml_frame)
    
    def toggle_log_panel(self):
        """Affiche ou masque le panneau LOG"""
        if self.show_log_panel.get():
            self.bottom_paned.add(self.log_frame, weight=1)
        else:
            self.bottom_paned.remove(self.log_frame)
    
    def clear_logs(self):
        """Effacer le contenu du panneau de logs"""
        self.log_text.delete(1.0, tk.END)
    
    def log_message(self, message, tag="info"):
        """Ajouter un message au panneau de logs avec le tag spécifié"""
        # Ajouter horodatage
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S] ")
        self.log_text.insert(tk.END, timestamp, "info")
        self.log_text.insert(tk.END, message + "\n", tag)
        self.log_text.see(tk.END)  # Faire défiler pour voir le nouveau message
    
    def insert_special_char(self, char):
        # Insérer le caractère spécial dans la zone de texte XML
        try:
            self.xml_text.insert(tk.INSERT, char)
            self.xml_text.highlight_syntax()
        except:
            pass
    
    def verify_xml(self):
        """Vérifier l'intégrité du XML et afficher les erreurs"""
        self.clear_logs()
        xml_content = self.xml_text.get(1.0, tk.END)
        
        # Supprimer les surlignages d'erreurs précédents
        self.xml_text.text.tag_remove("error", "1.0", "end")
        
        try:
            # Utiliser lxml pour la validation XML car il donne des messages d'erreur plus précis
            parser = etree.XMLParser()
            etree.fromstring(xml_content, parser)
            
            # Si on arrive ici, c'est que le XML est valide
            self.log_message("Le XML est valide et bien formé.", "success")
            
            # Mettre à jour la coloration syntaxique
            self.xml_text.highlight_syntax()
            
            # Mise à jour du statut
            self.status_bar.set_status("Validation XML réussie")
            
            return True
            
        except etree.XMLSyntaxError as e:
            # Afficher l'erreur dans les logs
            self.log_message(f"Erreur XML: {str(e)}", "error")
            
            # Surligner la ligne contenant l'erreur
            line_number = e.lineno if hasattr(e, 'lineno') else 1
            self.xml_text.highlight_error(line_number)
            
            # Mettre à jour la coloration syntaxique
            self.xml_text.highlight_syntax()
            
            # Mise à jour du statut
            self.status_bar.set_status("Erreur XML détectée")
            
            return False
            
        except Exception as e:
            self.log_message(f"Erreur lors de la validation: {str(e)}", "error")
            self.status_bar.set_status("Erreur de validation XML")
            return False
    
    def new_package(self):
        # Demander confirmation si le fichier actuel a été modifié
        if self.is_modified():
            if not messagebox.askyesno("Confirmer", "Des modifications non enregistrées seront perdues. Continuer ?"):
                return
        
        # Réinitialiser les données du paquet
        self.current_file = None
        self.package = Package()
        
        # Mettre à jour l'interface
        self.update_ui()
        
        # Générer le XML initial
        self.update_xml()
        
        # Effacer les logs
        self.clear_logs()
        self.log_message("Nouveau paquet créé.", "info")
        
        # Mettre à jour le titre de la fenêtre
        self.update_title()
        
        # Réinitialiser l'historique
        self.history = []
        self.history_position = -1
    
    def open_package(self):
        # Vérifier s'il y a des modifications non enregistrées
        if self.is_modified():
            if not messagebox.askyesno("Confirmer", "Des modifications non enregistrées seront perdues. Continuer ?"):
                return
        
        # Ouvrir un fichier XML
        file_path = filedialog.askopenfilename(
            filetypes=[("Fichiers XML", "*.xml"), ("Tous les fichiers", "*.*")]
        )
        
        if not file_path:
            return
        
        self.load_package_from_file(file_path)
    
    def load_package_from_file(self, file_path):
        try:
            # Lire le fichier XML
            with open(file_path, 'r', encoding='utf-8') as file:
                xml_content = file.read()
            
            # Analyser le contenu XML
            self.parse_xml(xml_content)
            
            # Mettre à jour l'interface
            self.update_ui()
            
            # Stocker le chemin du fichier actuel
            self.current_file = file_path
            
            # Mettre à jour la vue XML
            self.xml_text.delete(1.0, tk.END)
            self.xml_text.insert(tk.END, xml_content)
            self.xml_text.highlight_syntax()
            
            # Log
            self.clear_logs()
            self.log_message(f"Paquet chargé depuis {file_path}", "success")
            
            # Vérifier le XML
            self.verify_xml()
            
            # Ajouter aux fichiers récents
            self.add_recent_file(file_path)
            
            # Mettre à jour le titre de la fenêtre
            self.update_title()
            
            # Réinitialiser l'historique
            self.history = []
            self.history_position = -1
            
            return True
            
        except Exception as e:
            self.log_message(f"Échec du chargement: {str(e)}", "error")
            return False
    
    def save_package(self):
        # Sauvegarder dans le fichier actuel ou demander un nouveau fichier
        if not self.current_file:
            return self.save_package_as()
        else:
            try:
                # Récupérer le contenu XML actuel
                xml_content = self.xml_text.get(1.0, tk.END)
                
                # Sauvegarder dans le fichier
                with open(self.current_file, 'w', encoding='utf-8') as file:
                    file.write(xml_content)
                
                self.log_message(f"Paquet enregistré dans {self.current_file}", "success")
                self.status_bar.set_status(f"Enregistré dans {self.current_file}")
                
                # Mettre à jour le titre (enlever l'indicateur de modification)
                self.update_title(modified=False)
                
                return True
            except Exception as e:
                self.log_message(f"Échec de l'enregistrement: {str(e)}", "error")
                return False
    
    def save_package_as(self):
        # Demander un nouveau fichier pour sauvegarder
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xml",
            filetypes=[("Fichiers XML", "*.xml"), ("Tous les fichiers", "*.*")]
        )
        
        if not file_path:
            return False
        
        try:
            # Récupérer le contenu XML actuel
            xml_content = self.xml_text.get(1.0, tk.END)
            
            # Sauvegarder dans le fichier
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(xml_content)
            
            # Mettre à jour le fichier actuel
            self.current_file = file_path
            
            # Ajouter aux fichiers récents
            self.add_recent_file(file_path)
            
            self.log_message(f"Paquet enregistré dans {file_path}", "success")
            self.status_bar.set_status(f"Enregistré dans {file_path}")
            
            # Mettre à jour le titre
            self.update_title(modified=False)
            
            return True
        except Exception as e:
            self.log_message(f"Échec de l'enregistrement: {str(e)}", "error")
            return False
    
    def export_to_html(self):
        """Exporte le code XML actuel en HTML avec coloration syntaxique"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("Fichiers HTML", "*.html"), ("Tous les fichiers", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            # Récupérer le code XML
            xml_content = self.xml_text.get(1.0, tk.END)
            
            # Formater le XML pour une meilleure lisibilité
            try:
                parser = etree.XMLParser(remove_blank_text=True)
                root = etree.fromstring(xml_content.encode('utf-8'), parser)
                formatted_xml = etree.tostring(root, pretty_print=True, encoding='utf-8').decode('utf-8')
                
                # Préserver la déclaration XML
                xml_decl_match = re.match(r'<\?xml[^>]*\?>', xml_content)
                if xml_decl_match:
                    formatted_xml = xml_decl_match.group(0) + '\n\n' + formatted_xml
            except:
                # En cas d'erreur, utiliser le XML non formaté
                formatted_xml = xml_content
            
            # Utiliser Pygments pour la coloration syntaxique
            formatter = HtmlFormatter(style='colorful', full=True, linenos=True)
            highlighted = pygments.highlight(formatted_xml, XmlLexer(), formatter)
            
            # Écrire dans le fichier HTML
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(highlighted)
            
            self.log_message(f"XML exporté avec succès vers {file_path}", "success")
            
            # Ouvrir le fichier HTML dans le navigateur par défaut
            if messagebox.askyesno("Export réussi", f"XML exporté vers {file_path}. Ouvrir dans le navigateur?"):
                if platform.system() == "Windows":
                    os.startfile(file_path)
                elif platform.system() == "Darwin":  # macOS
                    subprocess.call(["open", file_path])
                else:  # Linux et autres
                    subprocess.call(["xdg-open", file_path])
        
        except Exception as e:
            self.log_message(f"Erreur lors de l'export HTML: {str(e)}", "error")
    
    def show_documentation(self):
        """Affiche la documentation de l'application"""
        try:
            if os.path.exists("documentation.md"):
                # Ouvrir la documentation avec le programme par défaut du système
                if platform.system() == "Windows":
                    os.startfile("documentation.md")
                elif platform.system() == "Darwin":  # macOS
                    subprocess.call(["open", "documentation.md"])
                else:  # Linux et autres
                    subprocess.call(["xdg-open", "documentation.md"])
            else:
                messagebox.showinfo("Documentation", 
                                  "La documentation n'est pas disponible. Veuillez consulter le fichier README.md.")
        except Exception as e:
            self.log_message(f"Erreur lors de l'ouverture de la documentation: {str(e)}", "error")
    
    def show_keyboard_shortcuts(self):
        """Affiche les raccourcis clavier de l'application"""
        shortcuts_text = """
Raccourcis clavier de l'Éditeur WPKG:

Fichier:
- Ctrl+N : Nouveau paquet
- Ctrl+O : Ouvrir un paquet
- Ctrl+S : Enregistrer
- Ctrl+Shift+S : Enregistrer sous...

Édition:
- Ctrl+Z : Annuler
- Ctrl+Y : Refaire
- Ctrl+X : Couper
- Ctrl+C : Copier
- Ctrl+V : Coller
- Ctrl+F : Rechercher/Remplacer

Affichage:
- Ctrl++ : Zoom +
- Ctrl+- : Zoom -
- Ctrl+0 : Taille par défaut

Outils:
- F7 : Vérifier XML
- F8 : Formater XML
"""
        messagebox.showinfo("Raccourcis clavier", shortcuts_text)
    
    def check_updates(self):
        """Vérifie si des mises à jour sont disponibles"""
        # Simulation de vérification de mise à jour
        self.log_message("Vérification des mises à jour...", "info")
        self.status_bar.set_status("Vérification des mises à jour...")
        
        # Simuler un délai pour l'animation
        self.root.after(1000, lambda: self.log_message("Vous utilisez déjà la dernière version (1.2).", "success"))
        self.root.after(1000, lambda: self.status_bar.set_status("Aucune mise à jour disponible"))
    
    def show_about(self):
        """Affiche les informations sur l'application"""
        about_msg = f"""WPKG Package Editor v1.2
        
Un éditeur graphique pour les paquets WPKG au format XML.

Cette application permet de créer, éditer et vérifier des paquets WPKG 
avec une interface utilisateur intuitive.

Python {platform.python_version()} - {platform.system()} {platform.release()}

© 2025
"""
        messagebox.showinfo("À propos", about_msg)
    
    def show_search_dialog(self):
        """Affiche le dialogue de recherche et remplacement"""
        search_dialog = SearchReplaceDialog(self.root, self.xml_text)
    
    def show_settings_dialog(self):
        """Affiche le dialogue des paramètres de l'application"""
        settings_dialog = tk.Toplevel(self.root)
        settings_dialog.title("Paramètres")
        settings_dialog.transient(self.root)
        settings_dialog.grab_set()
        settings_dialog.geometry("400x300")
        
        # Créer des frames pour les différentes sections
        general_frame = ttk.LabelFrame(settings_dialog, text="Général")
        general_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Thème
        ttk.Label(general_frame, text="Thème:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        theme_var = tk.StringVar(value=self.user_settings["theme"])
        theme_combo = ttk.Combobox(general_frame, textvariable=theme_var, 
                                 values=list(EditorTheme.THEMES.keys()))
        theme_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Sauvegarde automatique
        autosave_var = tk.BooleanVar(value=self.user_settings["autosave"])
        ttk.Checkbutton(general_frame, text="Sauvegarde automatique", 
                      variable=autosave_var).grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        
        # Intervalle de sauvegarde
        ttk.Label(general_frame, text="Intervalle (minutes):").grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        interval_var = tk.IntVar(value=self.user_settings["autosave_interval"])
        interval_spin = ttk.Spinbox(general_frame, from_=1, to=60, textvariable=interval_var, width=5)
        interval_spin.grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        
        # Taille de police
        ttk.Label(general_frame, text="Taille police XML:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        xml_font_var = tk.IntVar(value=self.user_settings["xml_font_size"])
        xml_font_spin = ttk.Spinbox(general_frame, from_=8, to=24, textvariable=xml_font_var, width=5)
        xml_font_spin.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(general_frame, text="Taille police Log:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        log_font_var = tk.IntVar(value=self.user_settings["log_font_size"])
        log_font_spin = ttk.Spinbox(general_frame, from_=8, to=24, textvariable=log_font_var, width=5)
        log_font_spin.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Boutons
        buttons_frame = ttk.Frame(settings_dialog)
        buttons_frame.pack(pady=10)
        
        def save_settings():
            self.user_settings["theme"] = theme_var.get()
            self.user_settings["autosave"] = autosave_var.get()
            self.user_settings["autosave_interval"] = interval_var.get()
            self.user_settings["xml_font_size"] = xml_font_var.get()
            self.user_settings["log_font_size"] = log_font_var.get()
            
            self.save_settings()
            self.apply_settings()
            settings_dialog.destroy()
        
        ttk.Button(buttons_frame, text="Enregistrer", command=save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Annuler", command=settings_dialog.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Réinitialiser", 
                 command=self.reset_settings).pack(side=tk.LEFT, padx=5)
    
    def reset_settings(self):
        """Réinitialiser les paramètres à leurs valeurs par défaut"""
        self.user_settings = {
            "theme": "clair",
            "autosave": False,
            "autosave_interval": 5,
            "xml_font_size": 10,
            "log_font_size": 10
        }
        self.save_settings()
        self.apply_settings()
    
    def save_settings(self):
        """Enregistrer les paramètres dans un fichier JSON"""
        try:
            with open("wpkg_editor_settings.json", "w", encoding="utf-8") as f:
                json.dump(self.user_settings, f, indent=4)
        except Exception as e:
            self.log_message(f"Erreur lors de l'enregistrement des paramètres: {str(e)}", "error")
    
    def load_settings(self):
        """Charger les paramètres depuis un fichier JSON"""
        try:
            if os.path.exists("wpkg_editor_settings.json"):
                with open("wpkg_editor_settings.json", "r", encoding="utf-8") as f:
                    loaded_settings = json.load(f)
                    # Mettre à jour les paramètres existants
                    for key, value in loaded_settings.items():
                        if key in self.user_settings:
                            self.user_settings[key] = value
        except Exception as e:
            self.log_message(f"Erreur lors du chargement des paramètres: {str(e)}", "error")
    
    def apply_settings(self):
        """Appliquer les paramètres actuels à l'interface"""
        # Appliquer le thème
        self.change_theme(self.user_settings["theme"])
        
        # Appliquer la taille des polices
        self.xml_text.text.configure(font=("TkFixedFont", self.user_settings["xml_font_size"]))
        self.log_text.configure(font=("TkFixedFont", self.user_settings["log_font_size"]))
        
        # Configurer la sauvegarde automatique
        if self.user_settings["autosave"]:
            self.start_autosave_timer()
        else:
            self.stop_autosave_timer()
    
    def change_theme(self, theme_name):
        """Changer le thème de l'application"""
        self.current_theme.set(theme_name)
        self.user_settings["theme"] = theme_name
        EditorTheme.apply_theme(self.root, theme_name, self.xml_text, self.log_text)
    
    def change_font_size(self, delta):
        """Changer la taille de la police du texte XML"""
        new_size = self.user_settings["xml_font_size"] + delta
        if 8 <= new_size <= 24:
            self.user_settings["xml_font_size"] = new_size
            self.xml_text.text.configure(font=("TkFixedFont", new_size))
    
    def reset_font_size(self):
        """Réinitialiser la taille de la police à la valeur par défaut"""
        self.user_settings["xml_font_size"] = 10
        self.xml_text.text.configure(font=("TkFixedFont", 10))
    
    def start_autosave_timer(self):
        """Démarrer le timer de sauvegarde automatique"""
        if self.autosave_timer:
            self.root.after_cancel(self.autosave_timer)
        
        # Convertir les minutes en millisecondes
        interval_ms = self.user_settings["autosave_interval"] * 60 * 1000
        
        def autosave_callback():
            if self.current_file and self.is_modified():
                self.save_package()
                self.log_message("Sauvegarde automatique effectuée", "info")
            
            # Reprogrammer le prochain autosave
            self.autosave_timer = self.root.after(interval_ms, autosave_callback)
        
        # Démarrer le timer
        self.autosave_timer = self.root.after(interval_ms, autosave_callback)
    
    def stop_autosave_timer(self):
        """Arrêter le timer de sauvegarde automatique"""
        if self.autosave_timer:
            self.root.after_cancel(self.autosave_timer)
            self.autosave_timer = None
    
    def is_modified(self):
        """Vérifier si le paquet actuel a été modifié depuis le dernier enregistrement"""
        # Pour l'instant, on considère toujours comme modifié si un fichier est ouvert
        # Une méthode plus sophistiquée pourrait comparer le contenu actuel avec le fichier
        return self.current_file is not None
    
    def update_title(self, modified=True):
        """Mettre à jour le titre de la fenêtre"""
        title = "WPKG Package Editor v1.2"
        
        if self.current_file:
            filename = os.path.basename(self.current_file)
            title = f"{filename} - {title}"
            
            if modified:
                title = f"*{title}"
        
        self.root.title(title)
    
    def update_cursor_position_from_text(self, event=None):
        """Mettre à jour la position du curseur dans la barre de statut"""
        try:
            pos = self.xml_text.text.index(tk.INSERT)
            line, col = pos.split('.')
            self.status_bar.update_cursor_position(line, col)
        except:
            pass
    
    def add_recent_file(self, file_path):
        """Ajouter un fichier à la liste des fichiers récents"""
        # Convertir en chemin absolu
        file_path = os.path.abspath(file_path)
        
        # Supprimer le fichier s'il est déjà dans la liste
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        
        # Ajouter le fichier au début de la liste
        self.recent_files.insert(0, file_path)
        
        # Limiter le nombre de fichiers récents
        if len(self.recent_files) > self.max_recent_files:
            self.recent_files = self.recent_files[:self.max_recent_files]
        
        # Mettre à jour le menu
        self.update_recent_files_menu()
        
        # Enregistrer la liste des fichiers récents
        self.save_recent_files()
    
    def update_recent_files_menu(self):
        """Mettre à jour le menu des fichiers récents"""
        # Effacer les entrées existantes
        self.recent_menu.delete(0, tk.END)
        
        if not self.recent_files:
            self.recent_menu.add_command(label="(Aucun fichier récent)", state=tk.DISABLED)
        else:
            for i, file_path in enumerate(self.recent_files):
                # Afficher le nom du fichier plutôt que le chemin complet
                filename = os.path.basename(file_path)
                self.recent_menu.add_command(
                    label=f"{i+1}: {filename}",
                    command=lambda fp=file_path: self.load_package_from_file(fp)
                )
            
            self.recent_menu.add_separator()
            self.recent_menu.add_command(label="Effacer la liste", command=self.clear_recent_files)
    
    def clear_recent_files(self):
        """Effacer la liste des fichiers récents"""
        self.recent_files = []
        self.update_recent_files_menu()
        self.save_recent_files()
    
    def save_recent_files(self):
        """Enregistrer la liste des fichiers récents"""
        try:
            with open("wpkg_editor_recent.json", "w", encoding="utf-8") as f:
                json.dump(self.recent_files, f, indent=4)
        except Exception as e:
            self.log_message(f"Erreur lors de l'enregistrement des fichiers récents: {str(e)}", "error")
    
    def load_recent_files(self):
        """Charger la liste des fichiers récents"""
        try:
            if os.path.exists("wpkg_editor_recent.json"):
                with open("wpkg_editor_recent.json", "r", encoding="utf-8") as f:
                    self.recent_files = json.load(f)
                    
                    # Vérifier que les fichiers existent toujours
                    self.recent_files = [f for f in self.recent_files if os.path.exists(f)]
        except Exception as e:
            self.log_message(f"Erreur lors du chargement des fichiers récents: {str(e)}", "error")
    
    def add_to_history(self):
        """Ajouter l'état actuel à l'historique des actions"""
        # Obtenir l'état actuel
        current_state = {
            'package': {
                'id': self.package.id,
                'name': self.package.name,
                'revision': self.package.revision,
                'date': self.package.date,
                'reboot': self.package.reboot,
                'category': self.package.category,
                'priority': self.package.priority,
                'variables': [asdict(var) for var in self.package.variables],
                'checks': [asdict(check) for check in self.package.checks],
                'installs': [asdict(cmd) for cmd in self.package.installs],
                'upgrades': [asdict(cmd) for cmd in self.package.upgrades],
                'removes': [asdict(cmd) for cmd in self.package.removes],
                'comments': self.package.comments,
                'xml_declaration': self.package.xml_declaration
            },
            'xml': self.xml_text.get(1.0, tk.END)
        }
        
        # Si nous sommes au milieu de l'historique, supprimer les actions qui suivent
        if self.history_position < len(self.history) - 1:
            self.history = self.history[:self.history_position + 1]
        
        # Ajouter l'état à l'historique
        self.history.append(current_state)
        self.history_position = len(self.history) - 1
        
        # Limiter la taille de l'historique
        if len(self.history) > self.max_history:
            self.history.pop(0)
            self.history_position -= 1
    
    def undo(self):
        """Annuler la dernière action"""
        if self.history_position > 0:
            self.history_position -= 1
            self.restore_state(self.history[self.history_position])
            self.status_bar.set_status("Action annulée")
        else:
            self.status_bar.set_status("Impossible d'annuler davantage")
    
    def redo(self):
        """Refaire la dernière action annulée"""
        if self.history_position < len(self.history) - 1:
            self.history_position += 1
            self.restore_state(self.history[self.history_position])
            self.status_bar.set_status("Action refaite")
        else:
            self.status_bar.set_status("Impossible de refaire davantage")
    
    def restore_state(self, state):
        """Restaurer un état précédent"""
        # Restaurer l'état du paquet
        pkg_state = state['package']
        self.package = Package(
            id=pkg_state['id'],
            name=pkg_state['name'],
            revision=pkg_state['revision'],
            date=pkg_state['date'],
            reboot=pkg_state['reboot'],
            category=pkg_state['category'],
            priority=pkg_state['priority'],
            variables=[Variable(**var) for var in pkg_state['variables']],
            checks=[Check(**check) for check in pkg_state['checks']],
            installs=[Command(**cmd) for cmd in pkg_state['installs']],
            upgrades=[Command(**cmd) for cmd in pkg_state['upgrades']],
            removes=[Command(**cmd) for cmd in pkg_state['removes']],
            comments=pkg_state['comments'],
            xml_declaration=pkg_state['xml_declaration']
        )
        
        # Restaurer le contenu XML
        self.xml_text.delete(1.0, tk.END)
        self.xml_text.insert(tk.END, state['xml'])
        self.xml_text.highlight_syntax()
        
        # Mettre à jour l'interface
        self.update_ui()
    
    def on_tree_button_press(self, event):
        """Gérer le début du glisser-déposer dans un treeview"""
        tree = event.widget
        if tree.identify_region(event.x, event.y) == "cell":
            tree.drag_start = tree.identify_row(event.y)
    
    def on_tree_motion(self, event):
        """Gérer le mouvement pendant un glisser-déposer"""
        tree = event.widget
        if hasattr(tree, 'drag_start') and tree.drag_start:
            if tree.identify_region(event.x, event.y) == "cell":
                tree.drag_current = tree.identify_row(event.y)
                if tree.drag_current != tree.drag_start:
                    # Changer l'apparence pour indiquer la position de dépose
                    tree.tag_configure('drag_highlight', background='light blue')
                    tree.tag_remove('drag_highlight', tree.get_children())
                    tree.tag_add('drag_highlight', tree.drag_current)
    
    def on_tree_button_release(self, event):
        """Terminer le glisser-déposer et réorganiser les éléments"""
        tree = event.widget
        if hasattr(tree, 'drag_start') and tree.drag_start:
            if hasattr(tree, 'drag_current') and tree.drag_current:
                if tree.drag_current != tree.drag_start:
                    # Réorganiser l'élément
                    item_to_move = tree.item(tree.drag_start)
                    tree.delete(tree.drag_start)
                    tree.insert('', tree.index(tree.drag_current), values=item_to_move['values'])
                    
                    # Mettre à jour la liste correspondante
                    if tree == self.installs_tree:
                        self.update_installs_from_tree()
                    elif tree == self.upgrades_tree:
                        self.update_upgrades_from_tree()
                    elif tree == self.removes_tree:
                        self.update_removes_from_tree()
            
            # Supprimer le tag de mise en évidence
            tree.tag_remove('drag_highlight', tree.get_children())
            
            # Réinitialiser les attributs de glisser-déposer
            if hasattr(tree, 'drag_start'):
                del tree.drag_start
            if hasattr(tree, 'drag_current'):
                del tree.drag_current
            
            # Mettre à jour le XML
            self.update_xml()
    
    def update_installs_from_tree(self):
        """Mettre à jour la liste des commandes d'installation à partir du Treeview"""
        new_installs = []
        for item_id in self.installs_tree.get_children():
            values = self.installs_tree.item(item_id)['values']
            cmd, include, timeout = values
            
            # Trouver l'élément correspondant pour récupérer exit_code
            exit_code = ""
            for install in self.package.installs:
                if install.cmd == cmd and install.include == include and install.timeout == timeout:
                    exit_code = install.exit_code
                    break
            
            new_installs.append(Command(cmd=cmd, include=include, timeout=timeout, exit_code=exit_code))
        
        self.package.installs = new_installs
    
    def update_upgrades_from_tree(self):
        """Mettre à jour la liste des commandes de mise à niveau à partir du Treeview"""
        new_upgrades = []
        for item_id in self.upgrades_tree.get_children():
            values = self.upgrades_tree.item(item_id)['values']
            include, cmd = values
            new_upgrades.append(Command(include=include, cmd=cmd))
        
        self.package.upgrades = new_upgrades
    
    def update_removes_from_tree(self):
        """Mettre à jour la liste des commandes de suppression à partir du Treeview"""
        new_removes = []
        for item_id in self.removes_tree.get_children():
            values = self.removes_tree.item(item_id)['values']
            cmd, timeout = values
            
            # Trouver l'élément correspondant pour récupérer exit_code
            exit_code = ""
            for remove in self.package.removes:
                if remove.cmd == cmd and remove.timeout == timeout:
                    exit_code = remove.exit_code
                    break
            
            new_removes.append(Command(cmd=cmd, timeout=timeout, exit_code=exit_code))
        
        self.package.removes = new_removes
    
    def export_logs(self):
        """Exporter les logs dans un fichier texte"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Fichiers texte", "*.txt"), ("Tous les fichiers", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            log_content = self.log_text.get(1.0, tk.END)
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(log_content)
            
            self.status_bar.set_status(f"Logs exportés vers {file_path}")
        except Exception as e:
            self.log_message(f"Erreur lors de l'export des logs: {str(e)}", "error")
    
    def load_logs(self):
        """Charger des logs depuis un fichier texte"""
        file_path = filedialog.askopenfilename(
            filetypes=[("Fichiers texte", "*.txt"), ("Fichiers log", "*.log"), ("Tous les fichiers", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                log_content = file.read()
            
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, log_content)
            
            self.status_bar.set_status(f"Logs chargés depuis {file_path}")
        except Exception as e:
            self.log_message(f"Erreur lors du chargement des logs: {str(e)}", "error")
    
    def generate_template(self):
        """Générer un paquet modèle"""
        template_type = simpledialog.askstring(
            "Type de modèle", 
            "Choisissez un type de modèle:\n- app_portable\n- logiciel_installable\n- personnalisé",
            initialvalue="app_portable"
        )
        
        if not template_type:
            return
        
        template_xml = ""
        
        if template_type.lower() == "app_portable":
            template_xml = '''<?xml version="1.0" encoding="iso-8859-1"?>

<packages>

<!--
Description de l'application portable
Liens vers les téléchargements
Instructions ou remarques importantes
-->

<package id = "application-app"
   name     = "Nom de l'application - APP"
   revision = "1.0.0.0"
   date     = "{date}"
   reboot   = "false"
   category = "Applications"
   priority = "20" >

  <variable name="APPNAME" value="Nom de l'application - APP" />
  <variable name="APPVERS" value="1.0.0" />

  <check type="file" condition="versionequalto" path="%SYSTEMDRIVE%\Logiciels\App\Application\App.exe" value="1.0.0.0" />

  <install include="remove" />
  <install cmd='7z.bat "%SYSTEMDRIVE%\Logiciels\App\Application" "%SOFTWARE%\App\Applications\App-1.0.0.7z"' timeout="600" />
  <install cmd='nircmd.exe shortcut "%SYSTEMDRIVE%\Logiciels\App\Application\App.exe" "~$folder.common_desktop$" "Application"' timeout="60" />
  <install cmd='"%SOFTWARE%\App\install-app.bat" "%APPNAME%" "%APPVERS%"' timeout="60" ><exit code="any" /></install>
  
  <upgrade include="install" />

  <remove cmd='nircmd.exe execmd del /F /Q "~$folder.common_desktop$\Application.lnk"' timeout="60" ><exit code="any" /></remove>
  <remove cmd='"%ComSpec%" /C rmdir /S /Q "%SYSTEMDRIVE%\Logiciels\App\Application"' timeout="60" ><exit code="any" /></remove>
  <remove cmd='"%SOFTWARE%\App\install-app.bat" "%APPNAME%" /remove' timeout="60" ><exit code="any" /></remove>
</package>

</packages>'''.format(date=datetime.datetime.now().strftime("%d/%m/%Y"))
        
        elif template_type.lower() == "logiciel_installable":
            template_xml = '''<?xml version="1.0" encoding="iso-8859-1"?>

<packages>

<!--
Description du logiciel installable
Liens vers les téléchargements
Options d'installation silencieuse
-->

<package id = "logiciel"
   name     = "Nom du logiciel"
   revision = "1.0.0.0"
   date     = "{date}"
   priority = "20"
   category = "Applications"
   reboot   = "false" >

  <variable name='APPFILE' value='logiciel-setup-x86.exe' architecture="x86" />
  <variable name='APPFILE' value='logiciel-setup-x64.exe' architecture="x64" />

  <check type="uninstall" condition="exists" path="Nom du logiciel 1.0.0" architecture="x86" />
  <check type="uninstall" condition="exists" path="Nom du logiciel 1.0.0 (64bit)" architecture="x64" />
  
  <install cmd='"%ComSpec%" /C start "Run" /WAIT "%SOFTWARE%\Applications\Logiciel\%APPFILE%" /S' timeout='900' ><exit code='any' /></install>

  <upgrade include="install" />

  <remove cmd='"%ComSpec%" /C start "Run" /WAIT "C:\\Program Files\\Logiciel\\uninstall.exe" /S' timeout='900' ><exit code='any' /></remove>
</package>

</packages>'''.format(date=datetime.datetime.now().strftime("%d/%m/%Y"))
        
        else:  # personnalisé
            template_xml = '''<?xml version="1.0" encoding="iso-8859-1"?>

<packages>

<!--
Description du paquet personnalisé
-->

<package id = "custom-package"
   name     = "Paquet Personnalisé"
   revision = "1.0.0.0"
   date     = "{date}"
   reboot   = "false"
   category = "Custom"
   priority = "10" >

  <variable name="VAR1" value="Valeur1" />
  <variable name="VAR2" value="Valeur2" />

  <check type="file" condition="exists" path="%SYSTEMDRIVE%\Chemin\Vers\Fichier.exe" />
  
  <install cmd='Commande d&apos;installation' timeout="300" />
  
  <upgrade include="install" />

  <remove cmd='Commande de désinstallation' timeout="300" />
</package>

</packages>'''.format(date=datetime.datetime.now().strftime("%d/%m/%Y"))
        
        # Mettre à jour l'interface avec le modèle
        self.xml_text.delete(1.0, tk.END)
        self.xml_text.insert(tk.END, template_xml)
        self.xml_text.highlight_syntax()
        
        # Analyser le contenu XML pour mettre à jour le modèle de données
        self.parse_xml(template_xml)
        
        # Mettre à jour l'interface
        self.update_ui()
        
        # Mettre à jour le statut
        self.status_bar.set_status(f"Modèle '{template_type}' généré")
        self.log_message(f"Modèle de paquet '{template_type}' généré avec succès", "success")
    
    def compare_packages(self):
        """Comparer le paquet actuel avec un autre paquet"""
        # Demander le fichier à comparer
        file_path = filedialog.askopenfilename(
            filetypes=[("Fichiers XML", "*.xml"), ("Tous les fichiers", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            # Lire le fichier XML
            with open(file_path, 'r', encoding='utf-8') as file:
                compare_xml = file.read()
            
            # Créer une nouvelle instance du paquet pour comparaison
            compare_package = Package()
            
            # Analyser le XML
            current_xml = self.xml_text.get(1.0, tk.END)
            
            # Créer une fenêtre pour afficher la comparaison
            compare_window = tk.Toplevel(self.root)
            compare_window.title("Comparaison de paquets")
            compare_window.geometry("800x600")
            
            # Utiliser un PanedWindow pour diviser la fenêtre
            paned = ttk.PanedWindow(compare_window, orient=tk.HORIZONTAL)
            paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Partie gauche: paquet actuel
            current_frame = ttk.LabelFrame(paned, text="Paquet actuel")
            paned.add(current_frame, weight=1)
            
            current_text = scrolledtext.ScrolledText(current_frame, wrap=tk.WORD)
            current_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            current_text.insert(tk.END, current_xml)
            current_text.configure(state="disabled")
            
            # Partie droite: paquet à comparer
            compare_frame = ttk.LabelFrame(paned, text=f"Paquet: {os.path.basename(file_path)}")
            paned.add(compare_frame, weight=1)
            
            compare_text = scrolledtext.ScrolledText(compare_frame, wrap=tk.WORD)
            compare_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            compare_text.insert(tk.END, compare_xml)
            compare_text.configure(state="disabled")
            
            # Boutons
            buttons_frame = ttk.Frame(compare_window)
            buttons_frame.pack(fill=tk.X, padx=10, pady=10)
            
            ttk.Button(buttons_frame, text="Fermer", command=compare_window.destroy).pack(side=tk.RIGHT)
            
            # Log
            self.log_message(f"Comparaison avec {os.path.basename(file_path)}", "info")
            
        except Exception as e:
            self.log_message(f"Erreur lors de la comparaison: {str(e)}", "error")
    
    def build_install_command(self):
        """Construit la commande d'installation en remplaçant les variables"""
        cmd = self.install_cmd.get()
        if not cmd:
            self.log_message("Aucune commande à construire.", "warning")
            return
        
        # Remplacer les variables du paquet
        for var in self.package.variables:
            cmd = cmd.replace(f"%{var.name}%", var.value)
        
        # Remplacer les variables système communes
        system_vars = {
            "SYSTEMDRIVE": "C:",
            "SOFTWARE": "C:\\Software",
            "ComSpec": "C:\\Windows\\System32\\cmd.exe"
        }
        
        for var_name, var_value in system_vars.items():
            cmd = cmd.replace(f"%{var_name}%", var_value)
        
        # Afficher la commande construite
        self.log_message("Commande construite:", "info")
        self.log_message(cmd, "cmd")
        
        return cmd
    
    def execute_install_command(self):
        """Exécute la commande d'installation construite (Windows uniquement)"""
        if platform.system() != "Windows":
            self.log_message("L'exécution de commandes n'est disponible que sous Windows.", "error")
            return
        
        cmd = self.build_install_command()
        if not cmd:
            return
        
        try:
            # Demander confirmation avant d'exécuter
            if not messagebox.askyesno("Exécuter commande", 
                                     f"Voulez-vous vraiment exécuter cette commande ?\n\n{cmd}"):
                return
            
            # Exécuter la commande
            self.log_message("Exécution de la commande...", "info")
            
            # Utiliser subprocess pour exécuter la commande
            process = subprocess.Popen(
                cmd, 
                shell=True,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            stdout, stderr = process.communicate()
            
            # Afficher les résultats
            if stdout:
                self.log_message("Sortie standard:", "info")
                self.log_message(stdout, "cmd")
            
            if stderr:
                self.log_message("Erreur standard:", "error")
                self.log_message(stderr, "error")
            
            if process.returncode == 0:
                self.log_message(f"Commande exécutée avec succès (code retour: {process.returncode})", "success")
            else:
                self.log_message(f"Commande exécutée avec erreur (code retour: {process.returncode})", "error")
                
        except Exception as e:
            self.log_message(f"Erreur lors de l'exécution de la commande: {str(e)}", "error")
    
    def build_upgrade_command(self):
        """Construit la commande de mise à niveau en remplaçant les variables"""
        cmd = self.upgrade_cmd.get()
        if not cmd:
            self.log_message("Aucune commande à construire.", "warning")
            return
        
        # Remplacer les variables du paquet
        for var in self.package.variables:
            cmd = cmd.replace(f"%{var.name}%", var.value)
        
        # Remplacer les variables système communes
        system_vars = {
            "SYSTEMDRIVE": "C:",
            "SOFTWARE": "C:\\Software",
            "ComSpec": "C:\\Windows\\System32\\cmd.exe"
        }
        
        for var_name, var_value in system_vars.items():
            cmd = cmd.replace(f"%{var_name}%", var_value)
        
        # Afficher la commande construite
        self.log_message("Commande construite:", "info")
        self.log_message(cmd, "cmd")
        
        return cmd
    
    def execute_upgrade_command(self):
        """Exécute la commande de mise à niveau construite (Windows uniquement)"""
        if platform.system() != "Windows":
            self.log_message("L'exécution de commandes n'est disponible que sous Windows.", "error")
            return
        
        cmd = self.build_upgrade_command()
        if not cmd:
            return
        
        # Code similaire à execute_install_command
        try:
            # Demander confirmation avant d'exécuter
            if not messagebox.askyesno("Exécuter commande", 
                                     f"Voulez-vous vraiment exécuter cette commande ?\n\n{cmd}"):
                return
            
            # Exécuter la commande
            self.log_message("Exécution de la commande...", "info")
            
            # Utiliser subprocess pour exécuter la commande
            process = subprocess.Popen(
                cmd, 
                shell=True,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            stdout, stderr = process.communicate()
            
            # Afficher les résultats
            if stdout:
                self.log_message("Sortie standard:", "info")
                self.log_message(stdout, "cmd")
            
            if stderr:
                self.log_message("Erreur standard:", "error")
                self.log_message(stderr, "error")
            
            if process.returncode == 0:
                self.log_message(f"Commande exécutée avec succès (code retour: {process.returncode})", "success")
            else:
                self.log_message(f"Commande exécutée avec erreur (code retour: {process.returncode})", "error")
                
        except Exception as e:
            self.log_message(f"Erreur lors de l'exécution de la commande: {str(e)}", "error")
    
    def build_remove_command(self):
        """Construit la commande de suppression en remplaçant les variables"""
        cmd = self.remove_cmd.get()
        if not cmd:
            self.log_message("Aucune commande à construire.", "warning")
            return
        
        # Remplacer les variables du paquet
        for var in self.package.variables:
            cmd = cmd.replace(f"%{var.name}%", var.value)
        
        # Remplacer les variables système communes
        system_vars = {
            "SYSTEMDRIVE": "C:",
            "SOFTWARE": "C:\\Software",
            "ComSpec": "C:\\Windows\\System32\\cmd.exe"
        }
        
        for var_name, var_value in system_vars.items():
            cmd = cmd.replace(f"%{var_name}%", var_value)
        
        # Afficher la commande construite
        self.log_message("Commande construite:", "info")
        self.log_message(cmd, "cmd")
        
        return cmd
    
    def execute_remove_command(self):
        """Exécute la commande de suppression construite (Windows uniquement)"""
        if platform.system() != "Windows":
            self.log_message("L'exécution de commandes n'est disponible que sous Windows.", "error")
            return
        
        cmd = self.build_remove_command()
        if not cmd:
            return
        
        # Code similaire à execute_install_command
        try:
            # Demander confirmation avant d'exécuter
            if not messagebox.askyesno("Exécuter commande", 
                                     f"Voulez-vous vraiment exécuter cette commande ?\n\n{cmd}"):
                return
            
            # Exécuter la commande
            self.log_message("Exécution de la commande...", "info")
            
            # Utiliser subprocess pour exécuter la commande
            process = subprocess.Popen(
                cmd, 
                shell=True,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            stdout, stderr = process.communicate()
            
            # Afficher les résultats
            if stdout:
                self.log_message("Sortie standard:", "info")
                self.log_message(stdout, "cmd")
            
            if stderr:
                self.log_message("Erreur standard:", "error")
                self.log_message(stderr, "error")
            
            if process.returncode == 0:
                self.log_message(f"Commande exécutée avec succès (code retour: {process.returncode})", "success")
            else:
                self.log_message(f"Commande exécutée avec erreur (code retour: {process.returncode})", "error")
                
        except Exception as e:
            self.log_message(f"Erreur lors de l'exécution de la commande: {str(e)}", "error")
    
    def set_current_date(self):
        """Mettre la date actuelle dans le champ date"""
        current_date = datetime.datetime.now().strftime("%d/%m/%Y")
        self.package_vars['date'].set(current_date)
    
    def parse_xml(self, xml_content):
        # Extraire la déclaration XML
        xml_decl_match = re.match(r'<\?xml[^>]*\?>', xml_content)
        if xml_decl_match:
            self.package.xml_declaration = xml_decl_match.group(0)
        
        # Extraire les commentaires
        self.package.comments = []
        comment_matches = re.findall(r'<!--(.*?)-->', xml_content, re.DOTALL)
        for comment in comment_matches:
            self.package.comments.append(comment.strip())
        
        # Analyser le XML avec ElementTree
        try:
            root = ET.fromstring(xml_content)
            
            # Extraire les données du paquet
            package_elem = root.find('.//package')
            if package_elem is not None:
                # Attributs du paquet
                self.package.id = package_elem.get('id', '')
                self.package.name = package_elem.get('name', '')
                self.package.revision = package_elem.get('revision', '')
                self.package.date = package_elem.get('date', '')
                self.package.reboot = package_elem.get('reboot', 'false')
                self.package.category = package_elem.get('category', '')
                self.package.priority = package_elem.get('priority', '')
                
                # Extraire les variables
                self.package.variables = []
                for var_elem in package_elem.findall('./variable'):
                    self.package.variables.append(Variable(
                        name=var_elem.get('name', ''),
                        value=var_elem.get('value', ''),
                        architecture=var_elem.get('architecture', '')
                    ))
                
                # Extraire les checks
                self.package.checks = []
                for check_elem in package_elem.findall('./check'):
                    self.package.checks.append(Check(
                        type=check_elem.get('type', ''),
                        condition=check_elem.get('condition', ''),
                        path=check_elem.get('path', ''),
                        value=check_elem.get('value', ''),
                        architecture=check_elem.get('architecture', '')
                    ))
                
                # Extraire les commandes d'installation
                self.package.installs = []
                for install_elem in package_elem.findall('./install'):
                    exit_code = ""
                    exit_elem = install_elem.find('./exit')
                    if exit_elem is not None:
                        exit_code = exit_elem.get('code', '')
                    
                    self.package.installs.append(Command(
                        cmd=install_elem.get('cmd', ''),
                        include=install_elem.get('include', ''),
                        timeout=install_elem.get('timeout', ''),
                        exit_code=exit_code
                    ))
                
                # Extraire les commandes de mise à niveau
                self.package.upgrades = []
                for upgrade_elem in package_elem.findall('./upgrade'):
                    self.package.upgrades.append(Command(
                        include=upgrade_elem.get('include', ''),
                        cmd=upgrade_elem.get('cmd', '')
                    ))
                
                # Extraire les commandes de suppression
                self.package.removes = []
                for remove_elem in package_elem.findall('./remove'):
                    exit_code = ""
                    exit_elem = remove_elem.find('./exit')
                    if exit_elem is not None:
                        exit_code = exit_elem.get('code', '')
                    
                    self.package.removes.append(Command(
                        cmd=remove_elem.get('cmd', ''),
                        timeout=remove_elem.get('timeout', ''),
                        exit_code=exit_code
                    ))
                
                return True
        except Exception as e:
            self.log_message(f"Erreur lors de l'analyse XML: {str(e)}", "error")
            return False
    
    def update_ui(self):
        # Mettre à jour l'onglet Général
        for key, var in self.package_vars.items():
            var.set(getattr(self.package, key))
        
        # Mettre à jour l'onglet Variables
        self.variables_tree.delete(*self.variables_tree.get_children())
        for var in self.package.variables:
            self.variables_tree.insert('', 'end', values=(var.name, var.value, var.architecture))
        
        # Mettre à jour l'onglet Checks
        self.checks_tree.delete(*self.checks_tree.get_children())
        for check in self.package.checks:
            self.checks_tree.insert('', 'end', values=(
                check.type, check.condition, check.path, check.value, check.architecture
            ))
        
        # Mettre à jour l'onglet Installs
        self.installs_tree.delete(*self.installs_tree.get_children())
        for install in self.package.installs:
            self.installs_tree.insert('', 'end', values=(install.cmd, install.include, install.timeout))
        
        # Mettre à jour l'onglet Upgrades
        self.upgrades_tree.delete(*self.upgrades_tree.get_children())
        for upgrade in self.package.upgrades:
            self.upgrades_tree.insert('', 'end', values=(upgrade.include, upgrade.cmd))
        
        # Mettre à jour l'onglet Removes
        self.removes_tree.delete(*self.removes_tree.get_children())
        for remove in self.package.removes:
            self.removes_tree.insert('', 'end', values=(remove.cmd, remove.timeout))
        
        # Mettre à jour l'onglet Commentaires
        self.comments_text.delete(1.0, tk.END)
        self.comments_text.insert(tk.END, '\n\n'.join(self.package.comments))
        
        # Mettre à jour le titre de la fenêtre
        self.update_title()
    
    def update_xml(self):
        # Récupérer les données du formulaire
        for key, var in self.package_vars.items():
            setattr(self.package, key, var.get())
        
        # Créer le XML
        root = ET.Element('packages')
        
        # Ajouter les commentaires
        if self.package.comments:
            comment_text = '<!--\n' + '\n\n'.join(self.package.comments) + '\n-->'
            
            # Note: ElementTree ne gère pas bien les commentaires, donc nous les ajouterons manuellement
            # lors de la conversion en texte
        
        # Ajouter l'élément package
        package = ET.SubElement(root, 'package')
        for key, value in asdict(self.package).items():
            if key in ["variables", "checks", "installs", "upgrades", "removes", "comments", "xml_declaration"]:
                continue
                
            if value:  # Ne pas ajouter les attributs vides
                package.set(key, value)
        
        # Ajouter les variables
        for var in self.package.variables:
            var_elem = ET.SubElement(package, 'variable')
            var_elem.set('name', var.name)
            var_elem.set('value', var.value)
            if var.architecture:
                var_elem.set('architecture', var.architecture)
        
        # Ajouter les checks
        for check in self.package.checks:
            check_elem = ET.SubElement(package, 'check')
            check_elem.set('type', check.type)
            check_elem.set('condition', check.condition)
            check_elem.set('path', check.path)
            if check.value:
                check_elem.set('value', check.value)
            if check.architecture:
                check_elem.set('architecture', check.architecture)
        
        # Ajouter les commandes d'installation
        for install in self.package.installs:
            install_elem = ET.SubElement(package, 'install')
            if install.cmd:
                install_elem.set('cmd', install.cmd)
            if install.include:
                install_elem.set('include', install.include)
            if install.timeout:
                install_elem.set('timeout', install.timeout)
            if install.exit_code:
                exit_elem = ET.SubElement(install_elem, 'exit')
                exit_elem.set('code', install.exit_code)
        
        # Ajouter les commandes de mise à niveau
        for upgrade in self.package.upgrades:
            upgrade_elem = ET.SubElement(package, 'upgrade')
            if upgrade.include:
                upgrade_elem.set('include', upgrade.include)
            if upgrade.cmd:
                upgrade_elem.set('cmd', upgrade.cmd)
        
        # Ajouter les commandes de suppression
        for remove in self.package.removes:
            remove_elem = ET.SubElement(package, 'remove')
            if remove.cmd:
                remove_elem.set('cmd', remove.cmd)
            if remove.timeout:
                remove_elem.set('timeout', remove.timeout)
            if remove.exit_code:
                exit_elem = ET.SubElement(remove_elem, 'exit')
                exit_elem.set('code', remove.exit_code)
        
        # Convertir en texte XML
        xml_str = minidom.parseString(ET.tostring(root, encoding='utf-8')).toprettyxml(indent="  ")
        
        # Ajouter la déclaration XML au début
        xml_str = self.package.xml_declaration + '\n\n' + xml_str
        
        # Insérer les commentaires après la balise <packages>
        if self.package.comments:
            comment_text = '\n<!--\n' + '\n\n'.join(self.package.comments) + '\n-->\n'
            xml_str = xml_str.replace('<packages>\n', '<packages>\n' + comment_text)
        
        # Mettre à jour la zone de texte XML
        self.xml_text.delete(1.0, tk.END)
        self.xml_text.insert(tk.END, xml_str)
        self.xml_text.highlight_syntax()
        
        # Ajouter à l'historique
        self.add_to_history()
        
        # Mettre à jour le titre (indique qu'il y a des modifications)
        self.update_title()
    
    def update_from_xml(self):
        # Récupérer le contenu XML de la zone de texte
        xml_content = self.xml_text.get(1.0, tk.END)
        
        try:
            # Analyser le contenu XML
            result = self.parse_xml(xml_content)
            
            if result:
                # Mettre à jour l'interface
                self.update_ui()
                
                self.log_message("Formulaire mis à jour depuis XML", "success")
                
                # Ajouter à l'historique
                self.add_to_history()
                
                # Vérifier le XML
                self.verify_xml()
            else:
                self.log_message("Échec de l'analyse XML. Vérifiez le format du XML.", "error")
        except Exception as e:
            self.log_message(f"Échec d'analyse XML: {str(e)}", "error")
    
    def format_xml(self):
        # Récupérer le contenu XML de la zone de texte
        xml_content = self.xml_text.get(1.0, tk.END)
        
        try:
            # Formater le XML avec lxml pour une meilleure indentation
            parser = etree.XMLParser(remove_blank_text=True)
            root = etree.fromstring(xml_content.encode('utf-8'), parser)
            formatted_xml = etree.tostring(root, pretty_print=True, encoding='utf-8').decode('utf-8')
            
            # Préserver la déclaration XML
            xml_decl_match = re.match(r'<\?xml[^>]*\?>', xml_content)
            if xml_decl_match:
                formatted_xml = xml_decl_match.group(0) + '\n\n' + formatted_xml
            
            # Préserver les commentaires (approximation - une solution plus robuste nécessiterait un analyseur qui préserve les commentaires)
            comment_matches = re.findall(r'<!--(.*?)-->', xml_content, re.DOTALL)
            if comment_matches and '<packages>' in formatted_xml:
                comment_text = '\n<!--\n' + '\n\n'.join(c.strip() for c in comment_matches) + '\n-->\n'
                formatted_xml = formatted_xml.replace('<packages>\n', '<packages>\n' + comment_text)
            
            # Mettre à jour la zone de texte XML
            self.xml_text.delete(1.0, tk.END)
            self.xml_text.insert(tk.END, formatted_xml)
            self.xml_text.highlight_syntax()
            
            self.log_message("XML formaté avec succès", "success")
        except Exception as e:
            self.log_message(f"Échec de formatage XML: {str(e)}", "error")
    
    def update_comments(self):
        # Récupérer le texte des commentaires
        comments_text = self.comments_text.get(1.0, tk.END).strip()
        
        # Diviser en commentaires distincts par double saut de ligne
        self.package.comments = [c.strip() for c in comments_text.split('\n\n') if c.strip()]
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commentaires mis à jour", "info")
    
    def on_variable_select(self, event):
        # Récupérer l'élément sélectionné
        selection = self.variables_tree.selection()
        if not selection:
            return
        
        # Récupérer les valeurs
        item = self.variables_tree.item(selection[0])
        values = item['values']
        
        # Mettre à jour les champs d'édition
        self.var_name.set(values[0])
        self.var_value.set(values[1])
        self.var_arch.set(values[2] if len(values) > 2 else '')
    
    def add_variable(self):
        # Récupérer les valeurs des champs
        name = self.var_name.get()
        value = self.var_value.get()
        arch = self.var_arch.get()
        
        if not name or not value:
            self.log_message("Erreur: Nom et Valeur sont requis pour une variable.", "error")
            return
        
        # Ajouter à la liste des variables
        self.package.variables.append(Variable(
            name=name,
            value=value,
            architecture=arch
        ))
        
        # Ajouter à l'arbre
        self.variables_tree.insert('', 'end', values=(name, value, arch))
        
        # Effacer les champs
        self.var_name.set('')
        self.var_value.set('')
        self.var_arch.set('')
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message(f"Variable '{name}' ajoutée", "success")
    
    def update_variable(self):
        # Récupérer l'élément sélectionné
        selection = self.variables_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune variable sélectionnée.", "error")
            return
        
        # Récupérer les valeurs des champs
        name = self.var_name.get()
        value = self.var_value.get()
        arch = self.var_arch.get()
        
        if not name or not value:
            self.log_message("Erreur: Nom et Valeur sont requis pour une variable.", "error")
            return
        
        # Mettre à jour l'arbre
        self.variables_tree.item(selection[0], values=(name, value, arch))
        
        # Mettre à jour la liste des variables
        item_index = self.variables_tree.index(selection[0])
        if 0 <= item_index < len(self.package.variables):
            self.package.variables[item_index] = Variable(
                name=name,
                value=value,
                architecture=arch
            )
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message(f"Variable '{name}' mise à jour", "success")
    
    def delete_variable(self):
        # Récupérer l'élément sélectionné
        selection = self.variables_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune variable sélectionnée.", "error")
            return
        
        # Récupérer le nom de la variable
        item = self.variables_tree.item(selection[0])
        var_name = item['values'][0]
        
        # Supprimer de l'arbre
        item_index = self.variables_tree.index(selection[0])
        self.variables_tree.delete(selection[0])
        
        # Supprimer de la liste des variables
        if 0 <= item_index < len(self.package.variables):
            del self.package.variables[item_index]
        
        # Effacer les champs
        self.var_name.set('')
        self.var_value.set('')
        self.var_arch.set('')
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message(f"Variable '{var_name}' supprimée", "info")
    
    def duplicate_variable(self):
        # Récupérer l'élément sélectionné
        selection = self.variables_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune variable sélectionnée à dupliquer.", "error")
            return
        
        # Récupérer les valeurs
        item = self.variables_tree.item(selection[0])
        values = item['values']
        
        name = values[0]
        value = values[1]
        arch = values[2] if len(values) > 2 else ''
        
        # Créer un nouveau nom pour la copie
        new_name = f"{name}_copy"
        
        # Ajouter à la liste des variables
        self.package.variables.append(Variable(
            name=new_name,
            value=value,
            architecture=arch
        ))
        
        # Ajouter à l'arbre
        self.variables_tree.insert('', 'end', values=(new_name, value, arch))
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message(f"Variable '{name}' dupliquée en '{new_name}'", "success")
    
    def on_check_select(self, event):
        # Récupérer l'élément sélectionné
        selection = self.checks_tree.selection()
        if not selection:
            return
        
        # Récupérer les valeurs
        item = self.checks_tree.item(selection[0])
        values = item['values']
        
        # Mettre à jour les champs d'édition
        self.check_type.set(values[0])
        self.check_condition.set(values[1])
        self.check_path.set(values[2])
        self.check_value.set(values[3] if len(values) > 3 else '')
        self.check_arch.set(values[4] if len(values) > 4 else '')
    
    def add_check(self):
        # Récupérer les valeurs des champs
        check_type = self.check_type.get()
        condition = self.check_condition.get()
        path = self.check_path.get()
        value = self.check_value.get()
        arch = self.check_arch.get()
        
        if not check_type or not condition or not path:
            self.log_message("Erreur: Type, Condition et Chemin sont requis pour une vérification.", "error")
            return
        
        # Ajouter à la liste des checks
        self.package.checks.append(Check(
            type=check_type,
            condition=condition,
            path=path,
            value=value,
            architecture=arch
        ))
        
        # Ajouter à l'arbre
        self.checks_tree.insert('', 'end', values=(check_type, condition, path, value, arch))
        
        # Effacer les champs
        self.check_type.set('')
        self.check_condition.set('')
        self.check_path.set('')
        self.check_value.set('')
        self.check_arch.set('')
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message(f"Vérification de type '{check_type}' ajoutée", "success")
    
    def update_check(self):
        # Récupérer l'élément sélectionné
        selection = self.checks_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune vérification sélectionnée.", "error")
            return
        
        # Récupérer les valeurs des champs
        check_type = self.check_type.get()
        condition = self.check_condition.get()
        path = self.check_path.get()
        value = self.check_value.get()
        arch = self.check_arch.get()
        
        if not check_type or not condition or not path:
            self.log_message("Erreur: Type, Condition et Chemin sont requis pour une vérification.", "error")
            return
        
        # Mettre à jour l'arbre
        self.checks_tree.item(selection[0], values=(check_type, condition, path, value, arch))
        
        # Mettre à jour la liste des checks
        item_index = self.checks_tree.index(selection[0])
        if 0 <= item_index < len(self.package.checks):
            self.package.checks[item_index] = Check(
                type=check_type,
                condition=condition,
                path=path,
                value=value,
                architecture=arch
            )
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message(f"Vérification de type '{check_type}' mise à jour", "success")
    
    def delete_check(self):
        # Récupérer l'élément sélectionné
        selection = self.checks_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune vérification sélectionnée.", "error")
            return
        
        # Récupérer le type de check
        item = self.checks_tree.item(selection[0])
        check_type = item['values'][0]
        
        # Supprimer de l'arbre
        item_index = self.checks_tree.index(selection[0])
        self.checks_tree.delete(selection[0])
        
        # Supprimer de la liste des checks
        if 0 <= item_index < len(self.package.checks):
            del self.package.checks[item_index]
        
        # Effacer les champs
        self.check_type.set('')
        self.check_condition.set('')
        self.check_path.set('')
        self.check_value.set('')
        self.check_arch.set('')
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message(f"Vérification de type '{check_type}' supprimée", "info")
    
    def duplicate_check(self):
        # Récupérer l'élément sélectionné
        selection = self.checks_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune vérification sélectionnée à dupliquer.", "error")
            return
        
        # Récupérer les valeurs
        item = self.checks_tree.item(selection[0])
        values = item['values']
        
        check_type = values[0]
        condition = values[1]
        path = values[2]
        value = values[3] if len(values) > 3 else ''
        arch = values[4] if len(values) > 4 else ''
        
        # Ajouter à la liste des checks
        self.package.checks.append(Check(
            type=check_type,
            condition=condition,
            path=path,
            value=value,
            architecture=arch
        ))
        
        # Ajouter à l'arbre
        self.checks_tree.insert('', 'end', values=(check_type, condition, path, value, arch))
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message(f"Vérification de type '{check_type}' dupliquée", "success")
    
    def on_install_select(self, event):
        # Récupérer l'élément sélectionné
        selection = self.installs_tree.selection()
        if not selection:
            return
        
        # Récupérer les valeurs
        item = self.installs_tree.item(selection[0])
        values = item['values']
        
        # Mettre à jour les champs d'édition
        self.install_cmd.set(values[0])
        self.install_include.set(values[1] if len(values) > 1 else '')
        self.install_timeout.set(values[2] if len(values) > 2 else '')
        
        # Récupérer le exit code depuis la liste des installs
        item_index = self.installs_tree.index(selection[0])
        if 0 <= item_index < len(self.package.installs):
            self.install_exit_code.set(self.package.installs[item_index].exit_code)
        else:
            self.install_exit_code.set('')
    
    def add_install(self):
        # Récupérer les valeurs des champs
        cmd = self.install_cmd.get()
        include = self.install_include.get()
        timeout = self.install_timeout.get()
        exit_code = self.install_exit_code.get()
        
        # Ajouter à la liste des installs
        self.package.installs.append(Command(
            cmd=cmd,
            include=include,
            timeout=timeout,
            exit_code=exit_code
        ))
        
        # Ajouter à l'arbre
        self.installs_tree.insert('', 'end', values=(cmd, include, timeout))
        
        # Effacer les champs
        self.install_cmd.set('')
        self.install_include.set('')
        self.install_timeout.set('')
        self.install_exit_code.set('')
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande d'installation ajoutée", "success")
    
    def update_install(self):
        # Récupérer l'élément sélectionné
        selection = self.installs_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune commande d'installation sélectionnée.", "error")
            return
        
        # Récupérer les valeurs des champs
        cmd = self.install_cmd.get()
        include = self.install_include.get()
        timeout = self.install_timeout.get()
        exit_code = self.install_exit_code.get()
        
        # Mettre à jour l'arbre
        self.installs_tree.item(selection[0], values=(cmd, include, timeout))
        
        # Mettre à jour la liste des installs
        item_index = self.installs_tree.index(selection[0])
        if 0 <= item_index < len(self.package.installs):
            self.package.installs[item_index] = Command(
                cmd=cmd,
                include=include,
                timeout=timeout,
                exit_code=exit_code
            )
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande d'installation mise à jour", "success")
    
    def delete_install(self):
        # Récupérer l'élément sélectionné
        selection = self.installs_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune commande d'installation sélectionnée.", "error")
            return
        
        # Supprimer de l'arbre
        item_index = self.installs_tree.index(selection[0])
        self.installs_tree.delete(selection[0])
        
        # Supprimer de la liste des installs
        if 0 <= item_index < len(self.package.installs):
            del self.package.installs[item_index]
        
        # Effacer les champs
        self.install_cmd.set('')
        self.install_include.set('')
        self.install_timeout.set('')
        self.install_exit_code.set('')
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande d'installation supprimée", "info")
    
    def duplicate_install(self):
        # Récupérer l'élément sélectionné
        selection = self.installs_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune commande d'installation sélectionnée à dupliquer.", "error")
            return
        
        # Récupérer les valeurs
        item = self.installs_tree.item(selection[0])
        values = item['values']
        
        cmd = values[0]
        include = values[1] if len(values) > 1 else ''
        timeout = values[2] if len(values) > 2 else ''
        
        # Récupérer le exit code depuis la liste des installs
        exit_code = ""
        item_index = self.installs_tree.index(selection[0])
        if 0 <= item_index < len(self.package.installs):
            exit_code = self.package.installs[item_index].exit_code
        
        # Ajouter à la liste des installs
        self.package.installs.append(Command(
            cmd=cmd,
            include=include,
            timeout=timeout,
            exit_code=exit_code
        ))
        
        # Ajouter à l'arbre
        self.installs_tree.insert('', 'end', values=(cmd, include, timeout))
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande d'installation dupliquée", "success")
    
    def on_upgrade_select(self, event):
        # Récupérer l'élément sélectionné
        selection = self.upgrades_tree.selection()
        if not selection:
            return
        
        # Récupérer les valeurs
        item = self.upgrades_tree.item(selection[0])
        values = item['values']
        
        # Mettre à jour les champs d'édition
        self.upgrade_include.set(values[0])
        self.upgrade_cmd.set(values[1] if len(values) > 1 else '')
    
    def add_upgrade(self):
        # Récupérer les valeurs des champs
        include = self.upgrade_include.get()
        cmd = self.upgrade_cmd.get()
        
        # Ajouter à la liste des upgrades
        self.package.upgrades.append(Command(
            include=include,
            cmd=cmd
        ))
        
        # Ajouter à l'arbre
        self.upgrades_tree.insert('', 'end', values=(include, cmd))
        
        # Effacer les champs
        self.upgrade_include.set('')
        self.upgrade_cmd.set('')
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande de mise à niveau ajoutée", "success")
    
    def update_upgrade(self):
        # Récupérer l'élément sélectionné
        selection = self.upgrades_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune commande de mise à niveau sélectionnée.", "error")
            return
        
        # Récupérer les valeurs des champs
        include = self.upgrade_include.get()
        cmd = self.upgrade_cmd.get()
        
        # Mettre à jour l'arbre
        self.upgrades_tree.item(selection[0], values=(include, cmd))
        
        # Mettre à jour la liste des upgrades
        item_index = self.upgrades_tree.index(selection[0])
        if 0 <= item_index < len(self.package.upgrades):
            self.package.upgrades[item_index] = Command(
                include=include,
                cmd=cmd
            )
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande de mise à niveau mise à jour", "success")
    
    def delete_upgrade(self):
        # Récupérer l'élément sélectionné
        selection = self.upgrades_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune commande de mise à niveau sélectionnée.", "error")
            return
        
        # Supprimer de l'arbre
        item_index = self.upgrades_tree.index(selection[0])
        self.upgrades_tree.delete(selection[0])
        
        # Supprimer de la liste des upgrades
        if 0 <= item_index < len(self.package.upgrades):
            del self.package.upgrades[item_index]
        
        # Effacer les champs
        self.upgrade_include.set('')
        self.upgrade_cmd.set('')
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande de mise à niveau supprimée", "info")
    
    def duplicate_upgrade(self):
        # Récupérer l'élément sélectionné
        selection = self.upgrades_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune commande de mise à niveau sélectionnée à dupliquer.", "error")
            return
        
        # Récupérer les valeurs
        item = self.upgrades_tree.item(selection[0])
        values = item['values']
        
        include = values[0]
        cmd = values[1] if len(values) > 1 else ''
        
        # Ajouter à la liste des upgrades
        self.package.upgrades.append(Command(
            include=include,
            cmd=cmd
        ))
        
        # Ajouter à l'arbre
        self.upgrades_tree.insert('', 'end', values=(include, cmd))
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande de mise à niveau dupliquée", "success")
    
    def on_remove_select(self, event):
        # Récupérer l'élément sélectionné
        selection = self.removes_tree.selection()
        if not selection:
            return
        
        # Récupérer les valeurs
        item = self.removes_tree.item(selection[0])
        values = item['values']
        
        # Mettre à jour les champs d'édition
        self.remove_cmd.set(values[0])
        self.remove_timeout.set(values[1] if len(values) > 1 else '')
        
        # Récupérer le exit code depuis la liste des removes
        item_index = self.removes_tree.index(selection[0])
        if 0 <= item_index < len(self.package.removes):
            self.remove_exit_code.set(self.package.removes[item_index].exit_code)
        else:
            self.remove_exit_code.set('')
    
    def add_remove(self):
        # Récupérer les valeurs des champs
        cmd = self.remove_cmd.get()
        timeout = self.remove_timeout.get()
        exit_code = self.remove_exit_code.get()
        
        # Ajouter à la liste des removes
        self.package.removes.append(Command(
            cmd=cmd,
            timeout=timeout,
            exit_code=exit_code
        ))
        
        # Ajouter à l'arbre
        self.removes_tree.insert('', 'end', values=(cmd, timeout))
        
        # Effacer les champs
        self.remove_cmd.set('')
        self.remove_timeout.set('')
        self.remove_exit_code.set('')
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande de suppression ajoutée", "success")
    
    def update_remove(self):
        # Récupérer l'élément sélectionné
        selection = self.removes_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune commande de suppression sélectionnée.", "error")
            return
        
        # Récupérer les valeurs des champs
        cmd = self.remove_cmd.get()
        timeout = self.remove_timeout.get()
        exit_code = self.remove_exit_code.get()
        
        # Mettre à jour l'arbre
        self.removes_tree.item(selection[0], values=(cmd, timeout))
        
        # Mettre à jour la liste des removes
        item_index = self.removes_tree.index(selection[0])
        if 0 <= item_index < len(self.package.removes):
            self.package.removes[item_index] = Command(
                cmd=cmd,
                timeout=timeout,
                exit_code=exit_code
            )
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande de suppression mise à jour", "success")
    
    def delete_remove(self):
        # Récupérer l'élément sélectionné
        selection = self.removes_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune commande de suppression sélectionnée.", "error")
            return
        
        # Supprimer de l'arbre
        item_index = self.removes_tree.index(selection[0])
        self.removes_tree.delete(selection[0])
        
        # Supprimer de la liste des removes
        if 0 <= item_index < len(self.package.removes):
            del self.package.removes[item_index]
        
        # Effacer les champs
        self.remove_cmd.set('')
        self.remove_timeout.set('')
        self.remove_exit_code.set('')
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande de suppression supprimée", "info")
    
    def duplicate_remove(self):
        # Récupérer l'élément sélectionné
        selection = self.removes_tree.selection()
        if not selection:
            self.log_message("Erreur: Aucune commande de suppression sélectionnée à dupliquer.", "error")
            return
        
        # Récupérer les valeurs
        item = self.removes_tree.item(selection[0])
        values = item['values']
        
        cmd = values[0]
        timeout = values[1] if len(values) > 1 else ''
        
        # Récupérer le exit code depuis la liste des removes
        exit_code = ""
        item_index = self.removes_tree.index(selection[0])
        if 0 <= item_index < len(self.package.removes):
            exit_code = self.package.removes[item_index].exit_code
        
        # Ajouter à la liste des removes
        self.package.removes.append(Command(
            cmd=cmd,
            timeout=timeout,
            exit_code=exit_code
        ))
        
        # Ajouter à l'arbre
        self.removes_tree.insert('', 'end', values=(cmd, timeout))
        
        # Mettre à jour le XML
        self.update_xml()
        
        self.log_message("Commande de suppression dupliquée", "success")
    
    def on_close(self):
        """Gestion de la fermeture de l'application"""
        # Vérifier s'il y a des modifications non enregistrées
        if self.is_modified():
            if not messagebox.askyesno("Confirmer", "Des modifications non enregistrées seront perdues. Quitter quand même?"):
                return
        
        # Arrêter le timer de sauvegarde automatique
        self.stop_autosave_timer()
        
        # Enregistrer les paramètres
        self.save_settings()
        
        # Fermer l'application
        self.root.destroy()


# Point d'entrée de l'application
def main():
    root = tk.Tk()
    app = WPKGEditor(root)
    
    # Configurer le gestionnaire d'événement pour fermeture propre
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    
    # Mettre à jour le statut
    app.status_bar.set_status("Prêt")
    app.log_message("Éditeur WPKG démarré", "info")
    
    root.mainloop()

if __name__ == "__main__":
    main()
