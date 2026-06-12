# UI screens — schedule overview & relationship panel (technical §7.2).
#
# Placeholder screens. These read from the session object and display
# data. No engine logic here — just Ren'Py screen language.

screen schedule_overview():
    tag menu
    modal True

    frame:
        xalign 0.5
        yalign 0.5
        xsize 800
        ysize 600
        has vbox spacing 10

        text "Week Schedule" size 28

        if fh.session and fh.session.schedule:
            for i, slot_info in enumerate(fh.session.slot_summary()):
                hbox:
                    spacing 20
                    $ btype = slot_info["block_type"].replace("_", " ").title()
                    text "[btype]" size 18 min_width 150

                    if slot_info["resolved"]:
                        text "[slot_info['resolved']]" size 16 color "#8f8"
                    elif slot_info["forced"]:
                        text "[slot_info['forced']] (forced)" size 16 color "#ff8"
                    else:
                        text "—" size 16 color "#888"

        textbutton "Close" action Hide("schedule_overview") xalign 0.5


screen relationship_panel():
    tag menu
    modal True

    frame:
        xalign 0.5
        yalign 0.5
        xsize 700
        ysize 500
        has vbox spacing 10

        text "Relationships" size 28

        if fh.session:
            $ player = fh.session.state.characters.get("player")
            if player:
                for cid, rel in player.relationships.items():
                    $ other = fh.session.state.characters.get(cid)
                    if other:
                        hbox:
                            spacing 20
                            text "[other.name]" size 18 min_width 200
                            $ trust_pct = "{:.0f}".format(rel.trust * 100)
                            $ fam_pct = "{:.0f}".format(rel.familiarity * 100)
                            text "Trust: [trust_pct]%" size 16
                            text "Familiarity: [fam_pct]%" size 16
                            text "[rel.dynamic.value]" size 14 color "#aaf"

        textbutton "Close" action Hide("relationship_panel") xalign 0.5


# Quick-access buttons overlaid during gameplay.
screen hud():
    hbox:
        xalign 1.0
        yalign 0.0
        spacing 10

        textbutton "Schedule" action Show("schedule_overview")
        textbutton "Relations" action Show("relationship_panel")
