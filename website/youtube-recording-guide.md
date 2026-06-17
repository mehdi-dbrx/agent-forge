# BrickForge YouTube Video - Recording Guide

## Order: Screen first. Voice after.

If you narrate first then match the screen, you'll rush clicks to keep up with your own voice, or have dead air while deploy takes 2 minutes. Record what happens, then describe what happened.

## Phase 1: Rehearse

Click through all 7 steps end to end without recording. One full pass. Note:
- Where things take time (deploy, provision, data gen)
- The exact click order for each section
- Any UI that needs setup beforehand (empty project, clean workspace)

## Phase 2: Screen Record

Record each section separately. Not one 10-minute take.

| Section | What to capture | Notes |
|---------|----------------|-------|
| Intro | Terminal: `pip install brickforge && brickforge`, app opens in browser | Clean terminal, no clutter |
| Connect | Workspace block, warehouse picker, schema picker | Have a workspace ready with a running warehouse |
| Generate | Data wizard: type domain, generate schemas, generate rows, provision | Let the AI run, capture the SSE output |
| Wire | Model picker, prompt editor, Genie block, Bricks toggles, MCP, Features | Click through each, don't linger |
| Deploy | Set name, hit deploy, watch terminal stream, app URL appears | Let it run full, you'll speed it up later |
| Portable | Export bundle, show zip in Finder, import on different workspace, deploy | Need two workspaces or two projects |
| Own the code | Source control block, GitHub push, show repo in browser, open in editor | Have a GitHub repo ready |
| Architecture | Show the architecture diagram from the website or a slide | Static screen, voice does the work |

## Phase 3: Edit the Screen Recordings

Before recording voice:
- Speed up boring parts: deploy waiting, pip install, provisioning. Use 4x or 8x in Resolve with a clock overlay or a "30 seconds later" jump cut
- Keep SSE terminal output visible but fast-forwarded (it looks cool)
- Zoom into the setup drawer when showing details. Full-screen app looks small on YouTube. Use Resolve transform/crop.
- Cut dead clicks, hesitations, loading spinners longer than 3 seconds
- Add section title cards between steps if you want (optional, Auto Caption might be enough)

## Phase 4: Record Voiceover

- Play your edited screen recording in Resolve
- Hit record on your mic
- Narrate what you see on screen
- Pause the playback when you need to think
- This is the trick: you're reacting to the video, not performing live. Your timing naturally matches because you're watching the action happen.

Record voice one section at a time. 60-second segments, not a 10-minute monologue. Easier to redo one section than start over.

Leave 2-3 seconds of silence between sections. Gives you clean cut points.

## Phase 5: Assemble

- Drop voiceover onto timeline above the screen recording
- Trim video to fit voice, not the other way around
- If narration for deploy is 40s but screen is 2 min, speed up the middle
- If narration runs long on wiring, add a beat where you pause on a UI element
- Add Auto Caption (Edit > Auto Caption in Resolve 19) for the punchy text overlays
- Style captions: bold, big, centered, colored keywords

## Screen Recording Settings

- 1080p, not 4K. Text is more readable when the UI isn't tiny on a phone screen.
- Dark mode on (the app looks better)
- Clean desktop, no notification popups
- Browser: hide bookmarks bar, use a clean tab
- Terminal: increase font size to 14-16pt for readability

## Before You Start Recording

Checklist:
- [ ] Fresh project (empty, no leftover state)
- [ ] Workspace connected with running warehouse
- [ ] Empty UC schema ready
- [ ] Foundation Model endpoint available
- [ ] GitHub repo created (empty or with README)
- [ ] Second workspace ready (for portable demo) or plan to fake it
- [ ] Microphone tested, room quiet
- [ ] Script printed or on second monitor

---

## YouTube Tutorials to Watch Before Recording

### Voiceover in DaVinci Resolve
- [Record your voice over directly into DaVinci Resolve | Version 20](https://www.youtube.com/watch?v=Aq2WrT1OFvU)
- [How to Record Voice Over in DaVinci Resolve 2025 | Quick & Easy](https://www.youtube.com/watch?v=5PyFZRUGBNY)
- [How to Record Voiceover in DaVinci Resolve (WITHOUT Fairlight!)](https://www.youtube.com/watch?v=IVyMOH3dPTk)
- [How to Record Voiceover Directly in DaVinci Resolve 20 (Full Tutorial)](https://www.youtube.com/watch?v=1u1aOilv25U)
- [How to RECORD VOICEOVERS in DaVinci Resolve (New 2025)](https://www.youtube.com/watch?v=kSDtTfn6g6U)

### Auto Captions & Animated Text Overlays
- [Animated Subtitles In DaVinci Resolve 20 | Full Tutorial](https://www.youtube.com/watch?v=ApKlyi18tVE)
- [Auto Subtitles in Free DaVinci Resolve 2026 | Auto Transcription + .srt Export](https://www.youtube.com/watch?v=T6fb4Dqg_VU)
- [Automatic Subtitles in the FREE Version of DaVinci Resolve](https://www.youtube.com/watch?v=5li9ATlKKp8)
- [How to Add Auto Subtitles in DaVinci Resolve 20 FREE (2 Minutes)](https://www.youtube.com/watch?v=e_URHPG2iSE)
- [Create VIRAL Text Effects in DaVinci Resolve! - Full Tutorial](https://www.youtube.com/watch?v=BwZFVOCBT1E)
- [Everything you NEED to know about Automatic Subtitles in DaVinci Resolve Studio 20](https://www.youtube.com/watch?v=y9hkjtO-Mn8)

### Software Demo Video Best Practices
- [How To Record A Software Demo (quick tutorial + tips)](https://www.youtube.com/watch?v=hDGhnIpCZAQ)
- [How to make a SaaS product demo video (2026)](https://www.youtube.com/watch?v=Edj_zj4U_9s)
- [Software Demo Videos - Tips!](https://www.youtube.com/watch?v=CWrIvL4mBtY)
- [Screen Recording Workflow](https://www.youtube.com/watch?v=ggIPlatSjpo)
- [The BEST AI Screen Recording Software for How-To Videos (2025)](https://www.youtube.com/watch?v=zqAt9Bkak-g)
