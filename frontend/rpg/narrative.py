"""Authored story scenes and voice direction for Archivebound Level One.

Keep plot facts here and gameplay state in ``window.py``. Dialogue should sound
spoken rather than engraved: characters answer from immediate wants, interrupt
the clean exposition, and leave some thoughts unfinished. The Clerk notices
physical details and uses dry humor when cornered. He begins with no working
knowledge of this world's magic, institutions, creatures, or vocabulary. Mara
is practical, guarded, and warmer than she intends; fear makes her precise,
not poetic. Registry systems remain literal and procedural. No person exists
merely to define lore.
"""

from __future__ import annotations


OPENING_DIALOGUE = (
    ("MARA, SENIOR CLERK", "You're finally awake."),
    ("LAST CLERK", "What happened to me? Where am I? Who are you?"),
    ("MARA", "I'll take those questions as a good sign that you don't have a concussion."),
    ("LAST CLERK", "What?"),
    ("MARA", "Can you sit up?"),
    ("LAST CLERK", "I can try. Who are you?"),
    ("MARA", "Mara Venn. Senior Clerk. At the moment, also your medic."),
    ("LAST CLERK", "Medic? Did I get hurt?"),
    ("MARA", "I was hoping you would tell me. I just found you lying there on the floor."),
    ("LAST CLERK", "Was it that bad?"),
    ("MARA", "Well, you seem rather spry. And you still have your clothes on. I say you're fine."),
    ("LAST CLERK", "And what about this lantern with blue flames?"),
    ("MARA", "Something very important, I assume. I tried to pry it out of your hands. But you would not let go of it, even unconscious."),
    ("LAST CLERK", "So I have excellent instincts and no name."),
    ("MARA", "For now, the Archive calls you the Last Clerk."),
    ("LAST CLERK", "Who is that?"),
    ("MARA", "What, not who. The Archive is what this place is called."),
    ("LAST CLERK", "This place? It talks?"),
    ("MARA", "You seem to be taking this surprisingly well."),
    ("LAST CLERK", "Well, I don't know where I am, so I don't know what's normal around here."),
    ("MARA", "We can work with that. Come here when the room stops tilting. We will start with what your feet remember."),
)


ROOM_INTROS = {
    "memory": (
        ("LAST CLERK", "These clocks don't work."),
        ("MARA, THROUGH THE LANTERN", "They used to. That was the tragedy."),
        ("LAST CLERK", "Seems too dramatic for a clock room, don't you think?"),
        ("MARA", "You'll get it soon. I have a feeling you'll be able to put this room back the way it was."),
        ("THE HALL OF MEMORY", "Somewhere behind the walls, three different hours begin to breathe."),
    ),
    "mercy": (
        ("RED TAPE WRAITH", "APPEAL RECEIVED. SUFFERING NOTED. RELIEF DENIED."),
        ("LAST CLERK", "Who even starts a conversation like that? I just got here."),
        ("RED TAPE WRAITH", "EFFICIENCY IS MERCY."),
        ("MARA", "Sounds like an awfully misguided notion. But be careful. People disappeared because of that ideology."),
    ),
    "order": (
        ("THE LOWER REGISTRY", "DOCKET VII-13: COMPLETE. ACCESS: UNNECESSARY."),
        ("LAST CLERK", "Is it talking to me?"),
        ("MARA, THROUGH THE LANTERN", "Yes. It wants you to leave."),
        ("LAST CLERK", "I haven't touched anything."),
        ("MARA", "That may be what worries it."),
        ("THE LOWER REGISTRY", "ACCUSATION RECORDED AS USER ERROR."),
        ("LAST CLERK", "I don't even know what the error was."),
        ("MARA", "Neither does it. Start with the name someone removed. We may learn why it wants you gone."),
    ),
}


VAULT_INTRO = (
    (0, 0, "THE PENDING", "Another clerk. Put the key down. Sit. Wait with the rest of us."),
    (1, 1, "LAST CLERK", "Who said that?"),
    (2, 2, "THE PENDING", "Look at the pages."),
    (3, 3, "THE PENDING", "Every name waited for an answer. Some died first. The Archive called that neutral."),
    (4, 4, "LAST CLERK", "Those pages are moving when you breathe. Pages should not breathe."),
    (5, 5, "THE PENDING", "I made sure they could not be ignored."),
    (6, 6, "LAST CLERK", "You kept their names. You did not give them a voice."),
    (7, 7, "THE PENDING", "Neither can you."),
)


DEFEAT_CINEMATIC = (
    (0, 0, "THE PENDING", "You came for an ending. Here is yours."),
    (1, 0, "MARA", "No."),
    (2, 0, "LAST CLERK", "Mara?"),
    (3, 0, "MARA", "Save the questions. Breathe when I tell you."),
)


VICTORY_CINEMATIC = (
    (0, 0, "THE PENDING", "Close me, and they disappear again."),
    (1, 0, "LAST CLERK", "No. You kept their names."),
    (2, 0, "LAST CLERK", "I am taking them with me."),
    (3, 0, "THE PENDING", "Then you inherit the waiting."),
    (4, 0, "LAST CLERK", "Then I will carry it. But I will not call it neutral."),
    (5, 0, "ARCHIVE", "The throne gives way. Paper lifts in a hot wind, each sheet carrying a name."),
)


MIMIC_INTRO = (
    (0, 0, "CENTRAL CHEST", "DOCKET ACCEPTED. OPENING REWARD COMPARTMENT."),
    (1, 1, "LAST CLERK", "A chest. Finally, something honest."),
    (2, 2, "MARA, THROUGH THE LANTERN", "You have known it for four seconds."),
    (3, 3, "CENTRAL CHEST", "CORRECTION: OPENING MOUTH."),
    (4, 4, "LAST CLERK", "There it is."),
)


LEVEL_EPILOGUE = (
    ("LAST CLERK", "These are names."),
    ("THE PENDING, IN SEVERAL VOICES", "We had names before we had case numbers."),
    ("MARA", "I knew the Vault kept unresolved petitions. I told myself that meant paper."),
    ("CODEX OF THE UNCLOSED", "Most entries have been scraped from the public registers. One blank entry is written in your hand."),
    ("LAST CLERK", "I do not recognize it."),
    ("MARA", "I know."),
    ("LAST CLERK", "You sound frightened."),
    ("MARA", "I am."),
    ("CODEX OF THE UNCLOSED", "NEXT JURISDICTION: THE COURT OF ERASED NAMES."),
    ("ORIN, AT THE FAR THRESHOLD", "You always did take the long way."),
    ("LAST CLERK", "Do I know you?"),
    ("ORIN", "Not anymore."),
)
