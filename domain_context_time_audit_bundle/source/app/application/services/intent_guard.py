from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.text import normalize_persian_text


@dataclass(frozen=True)
class IntentDecision:
    allowed: bool
    status: str
    domain: str
    intent: str
    confidence: float
    reply: str | None = None
    suggestions: tuple[str, ...] = ()

    def to_response(self) -> dict[str, Any]:
        return {
            "reply": (
                self.reply
                or "در حال حاضر امکان پردازش این درخواست وجود ندارد."
            ),
            "requiresConfirmation": False,
            "suggestions": list(self.suggestions),
            "data": {
                "intentGuard": {
                    "status": self.status,
                    "domain": self.domain,
                    "intent": self.intent,
                    "confidence": round(
                        self.confidence,
                        2,
                    ),
                }
            },
        }


class IntentGuard:
    """
    الگوریتم محافظ تشخیص درخواست.

    این کلاس قبل از فراخوانی سرویس غذا، منابع انسانی
    یا تردد اجرا می‌شود و از ورود درخواست‌های بی‌ربط،
    مبهم یا پشتیبانی‌نشده جلوگیری می‌کند.
    """

    # FOOD_FINAL_PART1_GUARD_V1
    CONTROL_REPLIES = {
        "بله",
        "آره",
        "اره",
        "خیر",
        "نه",
        "اوکی",
        "باشه",
        "تایید",
        "تأیید",
        "لغو",
        "انصراف",
        "ادامه بده",
        "انجام بده",
        "بررسی کن",
        "بیخیال",
        "بی خیال",
        "بله لطفا",
        "بله لطفاً",
        "بله انجام بده",
        "بله تایید میکنم",
        "بله تأیید میکنم",
        "تایید میکنم",
        "تأیید میکنم",
        "تایید می کنم",
        "تأیید می کنم",
        "لغو کن",
        "کنسل کن",
        "حذف کن",
        "نمیخوام",
        "نمی خواهم",
        "yes",
        "ok",
        "confirm",
        "cancel",
    }

    GREETING_PHRASES = {
        "سلام",
        "درود",
        "سلام خوبی",
        "صبح بخیر",
        "عصر بخیر",
        "شب بخیر",
    }

    HELP_TERMS = {
        "راهنما",
        "کمک",
        "چه کار میکنی",
        "چه کار می کنی",
        "چه کارهایی",
        "قابلیت",
        "چی بلدی",
        "چه امکاناتی",
    }

    DOMAIN_TERMS = {
        "FOOD": {
            "غذا": 4,
            "منو": 4,
            "ناهار": 3,
            "شام": 3,
            "خوراک": 2,
            "رستوران": 3,
            "رزرو غذا": 5,
            "غذای هفته": 5,
        },
        "LEAVE": {
            "مرخصی": 5,
            "ماموریت": 5,
            "مأموریت": 5,
            "اضافه کاری": 4,
            "اضافه‌کاری": 4,
            "استحقاقی": 3,
            "استعلاجی": 3,
            "ساعتی": 1,
        },
        "ATTENDANCE": {
            "تردد": 5,
            "ساعت زنی": 5,
            "ساعت‌زنی": 5,
            "ورود": 2,
            "خروج": 2,
            "ورود و خروج": 5,
        },
        "DAILY_BRIEF": {
            "گزارش امروز": 6,
            "خلاصه امروز": 6,
            "وضعیت امروز": 5,
            "گزارش روزانه": 6,
        },
    }

    READ_TERMS = {
        "نشان بده",
        "نمایش بده",
        "نمایش",
        "بگو",
        "ببین",
        "بررسی کن",
        "لیست",
        "وضعیت",
        "چقدر",
        "چه مقدار",
        "چی دارم",
        "نشون بده",
        "نشون",
        "چیه",
        "چی هست",
        "چی داریم",
        "چه غذایی",
        "بده",
        "بیار",
    }

    CREATE_TERMS = {
        "ثبت",
        "درخواست",
        "بزن",
        "ایجاد",
        "رزرو کن",
        "برام بگیر",
        "برایم بگیر",
        "سفارش بده",
        "ثبت کن",
        "ثبت شه",
        "ثبت شود",
        "ثبتش کن",
        "رزرو شه",
        "رزرو شود",
        "انتخاب کن",
        "انتخاب شه",
        "انتخاب شود",
        "انتخابش کن",
        "بگیرش",
    }

    DELETE_TERMS = {
        "حذف",
        "لغو",
        "کنسل",
        "انصراف",
    }

    RECOMMEND_TERMS = {
        "پیشنهاد",
        "چی بخور",
        "چه بخور",
        "بهترین غذا",
        "انتخاب مناسب",
        "مورد علاقه",
        "موردعلاقه",
        "درصد علاقه",
        "درصد تمایل",
    }

    RATING_TERMS = {
        "امتیاز",
        "ستاره",
        "نظر غذا",
        "کامنت",
    }

    BALANCE_TERMS = {
        "مانده مرخصی",
        "سهمیه مرخصی",
        "موجودی مرخصی",
    }

    HISTORY_TERMS = {
        "تاریخچه",
        "سوابق",
        "قبلا",
        "قبلاً",
        "در گذشته",
        "رزرو کرده بودم",
        "چی رزرو کرده بودم",
        "چه غذایی رزرو کرده بودم",
        "غذایی که خورده بودم",
        "ماه قبل",
        "هفته قبل",
        "سال قبل",
    }

    TIME_HINTS = {
        "امروز",
        "فردا",
        "پس فردا",
        "دیروز",
        "این هفته",
        "هفته بعد",
        "هفته قبل",
        "ماه قبل",
        "ماه بعد",
        "ساعت",
        "تاریخ",
        "شنبه",
        "یکشنبه",
        "یک شنبه",
        "دوشنبه",
        "دو شنبه",
        "سه شنبه",
        "سهشنبه",
        "چهارشنبه",
        "چهار شنبه",
        "پنجشنبه",
        "پنج شنبه",
        "جمعه",
    }

    UNSUPPORTED_BUSINESS_TERMS = {
        "حقوق",
        "فیش حقوقی",
        "حکم کارگزینی",
        "بیمه",
        "وام",
        "مزایا",
        "پاداش",
        "کارتابل",
        "قرارداد",
        "ارزیابی عملکرد",
        "سرویس رفت و آمد",
        "اتوبوس",
    }

    OUT_OF_SCOPE_TERMS = {
        "قیمت دلار",
        "قیمت طلا",
        "بورس",
        "آب و هوا",
        "هواشناسی",
        "فوتبال",
        "نتیجه بازی",
        "گوشی",
        "موبایل",
        "لپ تاپ",
        "ماشین",
        "خودرو",
        "آشپزی",
        "طرز تهیه",
        "فیلم",
        "موسیقی",
        "برنامه نویسی",
        "کدنویسی",
        "سیاسی",
        "انتخابات",
    }

    AMBIGUOUS_ACTION_TERMS = {
        "ثبت کن",
        "برام ثبت کن",
        "برایم ثبت کن",
        "بزن",
        "انجام بده",
        "لغو کن",
        "حذف کن",
        "بررسی کن",
        "ثبت شه",
        "ثبت شود",
        "ثبتش کن",
        "رزرو کن",
        "رزرو شه",
        "رزرو شود",
        "انتخاب کن",
        "انتخاب شه",
        "انتخاب شود",
        "انتخابش کن",
        "برام بگیر",
        "برایم بگیر",
        "سفارش بده",
        "نشون بده",
    }

    @staticmethod
    def _contains_any(
        text: str,
        terms: set[str],
    ) -> bool:
        return any(
            term in text
            for term in terms
        )

    @staticmethod
    def _score_terms(
        text: str,
        weighted_terms: dict[str, int],
    ) -> int:
        return sum(
            weight
            for term, weight in weighted_terms.items()
            if term in text
        )

    def analyze(
        self,
        raw_text: str,
    ) -> IntentDecision:
        text = normalize_persian_text(
            raw_text or ""
        ).strip()

        if not text:
            return IntentDecision(
                allowed=False,
                status="EMPTY",
                domain="UNKNOWN",
                intent="EMPTY_MESSAGE",
                confidence=1.0,
                reply=(
                    "لطفاً درخواست خود را به‌صورت متنی ارسال کنید."
                ),
            )

        if text in self.CONTROL_REPLIES:
            return IntentDecision(
                allowed=True,
                status="ALLOWED",
                domain="CONTROL",
                intent="CONFIRMATION_REPLY",
                confidence=1.0,
            )

        if (
            text in self.GREETING_PHRASES
            or self._contains_any(
                text,
                self.HELP_TERMS,
            )
        ):
            return IntentDecision(
                allowed=True,
                status="ALLOWED",
                domain="GENERAL",
                intent="GREETING_OR_HELP",
                confidence=1.0,
            )

        domain_scores = {
            domain: self._score_terms(
                text,
                terms,
            )
            for domain, terms in self.DOMAIN_TERMS.items()
        }

        positive_domains = [
            (
                domain,
                score,
            )
            for domain, score in domain_scores.items()
            if score > 0
        ]

        positive_domains.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        has_supported_domain = bool(
            positive_domains
        )

        if (
            not has_supported_domain
            and self._contains_any(
                text,
                self.UNSUPPORTED_BUSINESS_TERMS,
            )
        ):
            return IntentDecision(
                allowed=False,
                status="UNSUPPORTED",
                domain="ORGANIZATIONAL",
                intent="UNSUPPORTED_CAPABILITY",
                confidence=0.98,
                reply=(
                    "متأسفم، در حال حاضر این خدمت در حوزه "
                    "قابلیت‌های من قرار ندارد. من می‌توانم "
                    "در امور غذا، مرخصی، مأموریت و تردد "
                    "به شما کمک کنم."
                ),
                suggestions=(
                    "منوی غذای این هفته را نشان بده",
                    "مانده مرخصی من چقدر است؟",
                    "تردد امروز را نشان بده",
                ),
            )

        if (
            not has_supported_domain
            and self._contains_any(
                text,
                self.OUT_OF_SCOPE_TERMS,
            )
        ):
            return IntentDecision(
                allowed=False,
                status="OUT_OF_SCOPE",
                domain="OUT_OF_SCOPE",
                intent="UNRELATED_QUESTION",
                confidence=0.99,
                reply=(
                    "متأسفم، من فقط برای خدمات سازمانی "
                    "مرتبط با غذا، مرخصی، مأموریت و تردد "
                    "طراحی شده‌ام و قادر به پاسخ‌گویی به "
                    "این پرسش نیستم."
                ),
                suggestions=(
                    "چه قابلیت‌هایی داری؟",
                    "منوی غذای این هفته را نشان بده",
                    "گزارش امروز من را بساز",
                ),
            )

        if not has_supported_domain:
            has_ambiguous_action = (
                self._contains_any(
                    text,
                    self.AMBIGUOUS_ACTION_TERMS,
                )
                or (
                    self._contains_any(
                        text,
                        self.TIME_HINTS,
                    )
                    and (
                        self._contains_any(
                            text,
                            self.CREATE_TERMS,
                        )
                        or self._contains_any(
                            text,
                            self.DELETE_TERMS,
                        )
                    )
                )
            )

            if has_ambiguous_action:
                return IntentDecision(
                    allowed=True,
                    status="DEFERRED",
                    domain="UNKNOWN",
                    intent="DEFER_TO_NLU",
                    confidence=0.70,
                )

            return IntentDecision(
                allowed=False,
                status="OUT_OF_SCOPE",
                domain="OUT_OF_SCOPE",
                intent="UNKNOWN_OR_UNRELATED",
                confidence=0.75,
                reply=(
                    "متأسفم، این پرسش در محدوده خدمات فعلی "
                    "من نیست یا منظور آن را با اطمینان کافی "
                    "تشخیص ندادم. من در زمینه غذا، مرخصی، "
                    "مأموریت و تردد پاسخ‌گو هستم."
                ),
                suggestions=(
                    "چه قابلیت‌هایی داری؟",
                    "منوی غذای این هفته را نشان بده",
                    "مانده مرخصی من چقدر است؟",
                ),
            )

        top_domain, top_score = (
            positive_domains[0]
        )

        if len(positive_domains) > 1:
            second_domain, second_score = (
                positive_domains[1]
            )

            if (
                top_domain != "DAILY_BRIEF"
                and second_domain != "DAILY_BRIEF"
                and abs(
                    top_score - second_score
                ) <= 1
            ):
                return IntentDecision(
                    allowed=False,
                    status="AMBIGUOUS",
                    domain="MULTI_DOMAIN",
                    intent="MULTIPLE_REQUESTS",
                    confidence=0.88,
                    reply=(
                        "در پیام شما بیش از یک موضوع تشخیص داده شد. "
                        "لطفاً درخواست غذا، مرخصی، مأموریت یا تردد "
                        "را جداگانه ارسال کنید."
                    ),
                )

        if (
            top_domain == "FOOD"
            and self._contains_any(
                text,
                self.HISTORY_TERMS,
            )
        ):
            return IntentDecision(
                allowed=False,
                status="UNSUPPORTED",
                domain="FOOD",
                intent="FOOD_HISTORICAL_RESERVATION",
                confidence=0.98,
                reply=(
                    "متأسفم، در حال حاضر امکان بررسی رزرو غذای "
                    "تاریخ‌های گذشته را ندارم. می‌توانم منوی فعال "
                    "هفته، رزروهای فعلی و پیشنهادهای غذایی را "
                    "بررسی کنم."
                ),
                suggestions=(
                    "رزروهای فعال من را نشان بده",
                    "منوی غذای این هفته را نشان بده",
                    "برای این هفته غذا پیشنهاد بده",
                ),
            )

        intent = self._detect_intent(
            text,
            top_domain,
        )

        if intent == "DOMAIN_ONLY":
            domain_name = {
                "FOOD": "غذا",
                "LEAVE": "مرخصی یا مأموریت",
                "ATTENDANCE": "تردد",
                "DAILY_BRIEF": "گزارش روزانه",
            }.get(
                top_domain,
                "خدمت موردنظر",
            )

            return IntentDecision(
                allowed=False,
                status="AMBIGUOUS",
                domain=top_domain,
                intent=intent,
                confidence=0.82,
                reply=(
                    f"موضوع «{domain_name}» را تشخیص دادم، "
                    "اما مشخص نیست چه کاری باید انجام شود. "
                    "لطفاً درخواست خود را دقیق‌تر بیان کنید."
                ),
                suggestions=self._domain_suggestions(
                    top_domain
                ),
            )

        confidence = min(
            0.99,
            0.70 + (
                top_score * 0.04
            ),
        )

        return IntentDecision(
            allowed=True,
            status="ALLOWED",
            domain=top_domain,
            intent=intent,
            confidence=confidence,
        )

    def _detect_intent(
        self,
        text: str,
        domain: str,
    ) -> str:
        if domain == "DAILY_BRIEF":
            return "DAILY_BRIEF"

        if self._contains_any(
            text,
            self.BALANCE_TERMS,
        ):
            return "READ_BALANCE"

        if self._contains_any(
            text,
            self.RATING_TERMS,
        ):
            return "RATE"

        if self._contains_any(
            text,
            self.DELETE_TERMS,
        ):
            return "DELETE_OR_CANCEL"

        if self._contains_any(
            text,
            self.RECOMMEND_TERMS,
        ):
            return "RECOMMEND"

        if self._contains_any(
            text,
            self.CREATE_TERMS,
        ):
            return "CREATE_OR_RESERVE"

        if self._contains_any(
            text,
            self.READ_TERMS,
        ):
            return "READ"

        if domain == "FOOD" and (
            "منو" in text
            or "غذاها" in text
            or "غذای هفته" in text
        ):
            return "READ_MENU"

        if domain == "ATTENDANCE":
            return "READ_ATTENDANCE"

        return "DOMAIN_ONLY"

    @staticmethod
    def _domain_suggestions(
        domain: str,
    ) -> tuple[str, ...]:
        if domain == "FOOD":
            return (
                "منوی غذای این هفته را نشان بده",
                "برای این هفته غذا پیشنهاد بده",
                "رزروهای فعال من را نشان بده",
            )

        if domain == "LEAVE":
            return (
                "مانده مرخصی من چقدر است؟",
                "برای فردا مرخصی ثبت کن",
                "درخواست‌های مرخصی من را نشان بده",
            )

        if domain == "ATTENDANCE":
            return (
                "تردد امروز را نشان بده",
                "تردد ساعت 08:00 امروز را ثبت کن",
            )

        return (
            "گزارش امروز من را بساز",
        )
