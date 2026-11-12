# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Coletor: compromissos de uma agenda (Google Agenda, Outlook, iCloud) viram tarefas.

Toda agenda tem um endereço "iCal" (.ics) que pode ser lido sem senha e sem chave:

- Google Agenda: Configurações da agenda > "Endereço secreto no formato iCal".
- Outlook: Configurações > Calendário > Calendários compartilhados > Publicar > ICS.
- iCloud: compartilhar a agenda como "Agenda pública".

Esse endereço dá acesso de leitura à sua agenda: trate como uma senha. Ele fica no
_modulo.yaml, dentro do vault; se o seu vault vai para um repositório, que seja privado.

Configuração (em tarefas/_modulo.yaml):

    agendas:
      - nome: Pessoal
        url: https://calendar.google.com/calendar/ical/.../basic.ics
    dias_a_frente: 14        # até quando olhar

Limite: compromissos que se repetem ("toda terça") entram só na primeira data.
Para rotinas, use o coletor recorrentes.py.
"""

import datetime
import pathlib
import os

from _comum import CONFIG, avisar, baixar, emitir


def linhas(texto: str) -> list[str]:
    """No formato iCal, linha que começa com espaço é continuação da anterior."""
    juntas: list[str] = []
    for linha in texto.replace("\r\n", "\n").split("\n"):
        if linha[:1] in (" ", "\t") and juntas:
            juntas[-1] += linha[1:]
        else:
            juntas.append(linha)
    return juntas


def quando(valor: str, parametros: str) -> tuple[datetime.date, str] | None:
    """'20260115T143000Z' -> (data local, '11:30'). Dia inteiro devolve hora vazia."""
    valor = valor.strip()
    try:
        if "T" not in valor:
            return datetime.datetime.strptime(valor[:8], "%Y%m%d").date(), ""
        momento = datetime.datetime.strptime(valor[:15], "%Y%m%dT%H%M%S")
        if valor.endswith("Z"):  # horário universal: converte para o horário deste computador
            momento = momento.replace(tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
        return momento.date(), momento.strftime("%H:%M")
    except ValueError:
        return None


def texto_livre(valor: str) -> str:
    return valor.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").strip()


def eventos(texto: str) -> list[dict]:
    achados, atual = [], None
    for linha in linhas(texto):
        if linha == "BEGIN:VEVENT":
            atual = {}
        elif linha == "END:VEVENT" and atual is not None:
            achados.append(atual)
            atual = None
        elif atual is not None and ":" in linha:
            cabeca, valor = linha.split(":", 1)
            nome, _, parametros = cabeca.partition(";")
            if nome == "DTSTART":
                atual["inicio"] = quando(valor, parametros)
            elif nome in ("SUMMARY", "LOCATION", "UID", "DESCRIPTION", "STATUS"):
                atual[nome.lower()] = texto_livre(valor)
    return achados


def main() -> None:
    hoje = datetime.date.today()
    limite = hoje + datetime.timedelta(days=int(CONFIG.get("dias_a_frente") or 14))
    for agenda in CONFIG.get("agendas") or []:
        endereco = str(agenda.get("url") or "") if isinstance(agenda, dict) else str(agenda)
        if isinstance(agenda, dict) and agenda.get("variavel"):
            endereco = os.environ.get(str(agenda["variavel"]), "")
        nome = str(agenda.get("nome") or "agenda") if isinstance(agenda, dict) else "agenda"
        if not endereco:
            continue
        try:
            endereco = endereco.replace("webcal://", "https://")  # o mesmo arquivo, com outro prefixo
            if endereco.startswith(("http://", "https://")):
                bruto = baixar(endereco).decode("utf-8", errors="replace")
            else:  # também aceita um arquivo .ics do computador
                bruto = pathlib.Path(endereco).expanduser().read_text(encoding="utf-8", errors="replace")
        except Exception as erro:  # uma agenda fora do ar não impede as outras
            avisar(f"Não consegui ler a agenda '{nome}': {erro}")
            continue
        for evento in eventos(bruto):
            inicio = evento.get("inicio")
            if not inicio or not evento.get("summary") or evento.get("status") == "CANCELLED":
                continue
            dia, hora = inicio
            if not (hoje <= dia <= limite):
                continue
            detalhes = [f"Horário: {hora}" if hora else "Dia inteiro", f"Agenda: {nome}"]
            if evento.get("location"):
                detalhes.append(f"Local: {evento['location']}")
            corpo = "\n".join(detalhes)
            if evento.get("description"):
                corpo += "\n\n" + evento["description"][:600]
            emitir(
                id=f"agenda:{evento.get('uid') or evento['summary']}:{dia.isoformat()}",
                titulo=(f"{hora} " if hora else "") + evento["summary"],
                corpo=corpo,
                data=dia.isoformat(),
                tags=["agenda"],
            )


if __name__ == "__main__":
    main()
