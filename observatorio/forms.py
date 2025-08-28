# observatorio/forms.py

from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SelectField, FileField, SubmitField
)
from wtforms.validators import DataRequired, Length, Optional

class SubmitForm(FlaskForm):
    """Formulário para o envio de novos relatos."""
    titulo = StringField(
        'Título do Relato',
        validators=[DataRequired("O título é obrigatório."), Length(max=100)]
    )
    descricao = TextAreaField(
        'Descrição Detalhada',
        validators=[DataRequired("A descrição é obrigatória."), Length(max=2000)]
    )
    categoria = SelectField(
        'Categoria do Fenômeno',
        validators=[DataRequired("Selecione uma categoria.")],
        choices=[]  # As escolhas serão populadas na rota
    )
    local = SelectField(
        'Local da Ocorrência',
        validators=[DataRequired("Selecione um local.")],
        choices=[]  # As escolhas serão populadas na rota
    )
    outro_local_texto = StringField('Especifique o Local')
    imagem = FileField('Enviar Imagem (opcional, até 5MB)')
    audio = FileField('Enviar Áudio (opcional, até 10MB)')
    submit = SubmitField('Enviar Relato')

class CommentForm(FlaskForm):
    """Formulário para adicionar comentários."""
    texto = TextAreaField(
        'Seu Comentário',
        validators=[DataRequired("O comentário não pode estar vazio."), Length(max=1000)]
    )
    submit = SubmitField('Publicar Comentário')

class LendaForm(FlaskForm):
    """Formulário para adicionar ou editar lendas."""
    titulo = StringField(
        'Título da Lenda',
        validators=[DataRequired(), Length(max=150)]
    )
    descricao = TextAreaField(
        'Descrição',
        validators=[DataRequired()]
    )
    local = SelectField(
        'Local Associado',
        validators=[DataRequired()],
        choices=[]
    )
    imagem = FileField('Imagem da Lenda (opcional)')
    submit = SubmitField('Salvar Lenda')

class AdminActionForm(FlaskForm):
    """
    Formulário vazio usado apenas para proteção CSRF em ações de admin
    que não têm campos, como aprovar, deletar, etc.
    """
    submit = SubmitField('Confirmar')