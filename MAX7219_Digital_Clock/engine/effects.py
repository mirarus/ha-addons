class Effects:
    SUPPORTED = {"static", "scroll", "marquee", "blink", "invert", "wave"}

    @classmethod
    def normalize(cls, value):
        effect = str(value or "static").strip().lower()
        if effect not in cls.SUPPORTED:
            return "static"
        return effect

    @staticmethod
    def _safe_text(text):
        return str(text or " ")

    @classmethod
    def render(cls, effect, text, frame):
        safe_effect = cls.normalize(effect)
        safe_text = cls._safe_text(text)

        if safe_effect in {"scroll", "marquee"}:
            return cls.marquee(safe_text, frame)
        if safe_effect == "blink":
            return cls.blink(safe_text, frame)
        if safe_effect == "invert":
            return cls.invert(safe_text, frame)
        if safe_effect == "wave":
            return cls.wave(safe_text, frame)
        return safe_text

    @staticmethod
    def blink(text, frame):
        return text if frame % 2 == 0 else " "

    @staticmethod
    def invert(text, frame):
        _ = frame
        return text[::-1]

    @staticmethod
    def marquee(text, frame):
        if not text:
            return " "
        index = frame % len(text)
        return f"{text[index:]} {text[:index]}".strip() or " "

    @staticmethod
    def wave(text, frame):
        if not text:
            return " "
        # Lightweight wave effect for low-power render loops.
        chars = []
        for idx, char in enumerate(text):
            chars.append(char if (idx + frame) % 2 == 0 else " ")
        rendered = "".join(chars).strip()
        return rendered or text