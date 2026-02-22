from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, List


class Translator:
    def __init__(self, enabled: bool = True, cache_dir: str = "cache/argos"):
        self.enabled = enabled
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.available = False
        self.translator = None
        if enabled:
            self._init_argos()

    def _init_argos(self) -> None:
        try:
            os.environ.setdefault("ARGOS_PACKAGES_DIR", str(self.cache_dir))
            from argostranslate import package, translate  # type: ignore

            installed_langs = translate.get_installed_languages()
            en_lang = next((l for l in installed_langs if l.code == "en"), None)
            zh_lang = next((l for l in installed_langs if l.code in {"zh", "zh_cn", "zh-CN"}), None)

            if not (en_lang and zh_lang and en_lang.get_translation(zh_lang)):
                logging.info("Argos en->zh model not installed. Attempting download/install...")
                package.update_package_index()
                available_packages = package.get_available_packages()
                pkg = next(
                    (
                        p
                        for p in available_packages
                        if p.from_code == "en" and p.to_code in {"zh", "zh_cn", "zh-CN"}
                    ),
                    None,
                )
                if pkg:
                    path = pkg.download()
                    package.install_from_path(path)
                else:
                    logging.warning("No en->zh Argos package found.")

            installed_langs = translate.get_installed_languages()
            en_lang = next((l for l in installed_langs if l.code == "en"), None)
            zh_lang = next((l for l in installed_langs if l.code.startswith("zh")), None)
            if en_lang and zh_lang:
                self.translator = en_lang.get_translation(zh_lang)
                self.available = self.translator is not None

            if not self.available:
                logging.warning("Translation unavailable; Chinese fields will be empty.")
        except Exception as exc:
            logging.warning("Argos initialization failed (%s). Chinese output disabled.", exc)
            self.available = False

    def translate_text(self, text: str) -> str:
        if not self.enabled or not self.available or not self.translator:
            return ""
        if not text.strip():
            return ""
        try:
            return self.translator.translate(text)
        except Exception as exc:
            logging.warning("Translation failed: %s", exc)
            return ""

    def translate_many(self, texts: Iterable[str]) -> List[str]:
        return [self.translate_text(t) for t in texts]
