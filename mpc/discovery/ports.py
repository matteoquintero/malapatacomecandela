# mpc/discovery/ports.py
# -*- coding: utf-8 -*-
"""
Puertos de salida del Bounded Context Discovery (Arquitectura Hexagonal).

Cada puerto define el contrato que el dominio necesita satisfacer — sin
importar qué adaptador de infraestructura lo implementa.

Puertos definidos:
  IMusicCatalogPort  — grabaciones, artistas, releases (MusicBrainz, etc.)
  IStyleCatalogPort  — búsqueda por estilos/géneros (Discogs, etc.)

Los adaptadores concretos viven en mpc/sources/:
  mpc.sources.musicbrainz  → implementa IMusicCatalogPort
  mpc.sources.discogs      → implementa IStyleCatalogPort (indirectamente)

Las estrategias en mpc/discovery/strategies/ dependen de estos puertos,
no de los adaptadores directamente.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IMusicCatalogPort(ABC):
    """
    Puerto de salida: catálogo de grabaciones musicales.

    Abstrae fuentes como MusicBrainz que proveen metadatos de artistas,
    grabaciones y releases con tags de género.
    """

    @abstractmethod
    def search_artists_by_tag(self, tag: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Busca artistas etiquetados con un tag de género.

        Returns:
            Lista de dicts con al menos {"id": str, "name": str}.
        """
        ...

    @abstractmethod
    def get_artist_recordings(self, mbid: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retorna las grabaciones de un artista por su MBID.

        Returns:
            Lista de dicts con al menos {"id": str, "title": str,
            "first-release-date": Optional[str]}.
        """
        ...

    @abstractmethod
    def search_recordings_by_tag(self, tag: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Busca grabaciones directamente por tag de género.

        Returns:
            Lista de dicts con al menos {"id": str, "title": str,
            "artist-credit": list}.
        """
        ...

    @abstractmethod
    def search_releases_by_tag(self, tag: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Busca releases etiquetados con un tag de género.

        Returns:
            Lista de dicts con al menos {"id": str, "title": str}.
        """
        ...

    @abstractmethod
    def get_release_tracklist(self, release_id: str) -> List[Dict[str, Any]]:
        """
        Retorna el tracklist de un release.

        Returns:
            Lista de dicts con al menos {"title": str, "artist": str}.
        """
        ...


class IStyleCatalogPort(ABC):
    """
    Puerto de salida: catálogo de estilos musicales.

    Abstrae fuentes como Discogs que permiten búsquedas por estilo/género
    y retornan releases con pares artista-canción.
    """

    @abstractmethod
    def search_by_style(
        self,
        style: str,
        release_type: str = "single",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Busca releases de un estilo específico.

        Args:
            style:        Nombre del estilo (ej: "Salsa", "Mambo").
            release_type: "single" | "release" | "album".
            limit:        Máximo de resultados.

        Returns:
            Lista de dicts con al menos {"artist": str, "title": str,
            "year": Optional[int], "country": Optional[str]}.
        """
        ...

    @abstractmethod
    def search_by_artist(self, artist: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Busca releases de un artista.

        Returns:
            Lista de dicts con al menos {"artist": str, "title": str,
            "year": Optional[int]}.
        """
        ...
