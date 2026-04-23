import re
from io import BytesIO
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import RolePermission, make_permission
from apps.core.views import TenantQueryMixin

from .models import Prescription, PrescriptionItem
from .serializers import PrescriptionSerializer, PrescriptionItemWriteSerializer


class PrescriptionListCreateView(TenantQueryMixin, generics.ListCreateAPIView):
    serializer_class = PrescriptionSerializer
    permission_classes = [RolePermission]
    resource_name = "prescription"

    def get_queryset(self):
        queryset = Prescription.objects.for_organization(
            self.request.user.organization
        ).select_related('pet', 'veterinarian', 'medical_record')
        pet_id = self.request.query_params.get('pet')
        if pet_id:
            queryset = queryset.filter(pet_id=pet_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            veterinarian=self.request.user,
        )


class PrescriptionDetailView(TenantQueryMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PrescriptionSerializer
    permission_classes = [RolePermission]
    resource_name = "prescription"

    def get_queryset(self):
        return Prescription.objects.for_organization(self.request.user.organization)


class PrescriptionByPetView(TenantQueryMixin, generics.ListAPIView):
    serializer_class = PrescriptionSerializer
    permission_classes = [RolePermission]
    resource_name = "prescription"

    def get_queryset(self):
        return Prescription.objects.for_organization(
            self.request.user.organization
        ).filter(pet_id=self.kwargs['pet_id'])


class PrescriptionItemCreateView(generics.CreateAPIView):
    serializer_class = PrescriptionItemWriteSerializer
    permission_classes = [RolePermission]
    resource_name = "prescription"

    def perform_create(self, serializer):
        prescription = get_object_or_404(
            Prescription,
            pk=self.kwargs['prescription_pk'],
            organization=self.request.user.organization,
        )
        serializer.save(prescription=prescription)


class PrescriptionItemDeleteView(generics.DestroyAPIView):
    permission_classes = [RolePermission]
    resource_name = "prescription"

    def get_object(self):
        prescription = get_object_or_404(
            Prescription,
            pk=self.kwargs['prescription_pk'],
            organization=self.request.user.organization,
        )
        return get_object_or_404(
            PrescriptionItem,
            pk=self.kwargs['pk'],
            prescription=prescription,
        )


@api_view(['GET'])
@permission_classes([make_permission("prescription.retrieve")])
def prescription_pdf(request, pk):
    """Genera y retorna la receta como archivo PDF."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
    except ImportError:
        return Response(
            {'error': 'reportlab no está instalado. Ejecuta: pip install reportlab'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    prescription = get_object_or_404(
        Prescription,
        pk=pk,
        organization=request.user.organization,
    )

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    margin = 2.5 * cm
    y = height - margin

    def draw_line(text, font='Helvetica', size=11, offset=16):
        nonlocal y
        c.setFont(font, size)
        c.drawString(margin, y, text)
        y -= offset

    def separator(offset=12):
        nonlocal y
        c.line(margin, y, width - margin, y)
        y -= offset

    draw_line(prescription.organization.name, font='Helvetica-Bold', size=16, offset=20)
    draw_line('RECETA MÉDICA VETERINARIA', font='Helvetica-Bold', size=13, offset=14)
    draw_line(
        f"Fecha: {prescription.created_at.strftime('%d/%m/%Y')}",
        size=10,
        offset=18,
    )
    separator()

    vet = prescription.veterinarian
    vet_name = f"{vet.first_name} {vet.last_name}".strip() or vet.username
    draw_line('Veterinario', font='Helvetica-Bold', size=11, offset=16)
    draw_line(vet_name, offset=14)
    if vet.specialty:
        draw_line(f"Especialidad: {vet.specialty}", size=10, offset=18)
    else:
        y -= 6
    separator()

    pet = prescription.pet
    draw_line('Paciente', font='Helvetica-Bold', size=11, offset=16)
    draw_line(f"Nombre: {pet.name}   Especie: {pet.species}   Raza: {pet.breed}", offset=14)
    draw_line(f"Propietario: {pet.owner.name}   Teléfono: {pet.owner.phone}", size=10, offset=18)
    separator()

    draw_line('Medicamentos', font='Helvetica-Bold', size=12, offset=18)
    for i, item in enumerate(prescription.items.select_related('product').all(), 1):
        unit = item.product.unit or ''
        draw_line(
            f"{i}. {item.product.name}  —  {item.quantity} {unit}".strip(),
            font='Helvetica-Bold',
            size=11,
            offset=15,
        )
        draw_line(f"   Dosis: {item.dose}", size=10, offset=13)
        if item.duration:
            draw_line(f"   Duración: {item.duration}", size=10, offset=13)
        if item.instructions:
            draw_line(f"   Instrucciones: {item.instructions}", size=10, offset=13)
        y -= 6

    if prescription.notes:
        separator()
        draw_line('Notas', font='Helvetica-Bold', size=11, offset=16)
        draw_line(prescription.notes, size=10, offset=14)

    y -= 30
    c.line(margin, y, margin + 180, y)
    y -= 14
    draw_line(vet_name, size=10, offset=12)
    if vet.specialty:
        draw_line(vet.specialty, size=9, offset=12)

    c.save()
    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type='application/pdf')
    safe_name = re.sub(r'[^\w\s\-]', '', pet.name)[:50]
    response['Content-Disposition'] = (
        f'attachment; filename="receta_{prescription.id}_{safe_name}.pdf"'
    )
    return response
