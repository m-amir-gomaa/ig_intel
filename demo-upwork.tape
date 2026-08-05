Output assets/demo/demo-upwork.gif

Set Shell "bash"
Set FontSize 18
Set Width 1200
Set Height 750
Set FontFamily "JetBrainsMono Nerd Font"
Set Theme "Dracula"
Set Padding 24
Set WindowBar Colorful
Set CursorBlink false
Set TypingSpeed 30ms
Set Framerate 10

# Clean prompt off-screen
Hide
Type "export PS1='$ '"
Enter
Type "cd ~/Projects/instaScript"
Enter
Type "rm -rf ~/ig_intel/Inbox/*"
Enter
Show

Type "bin/instascript assets/demo/instascript-demo-reel.mp4"
Enter
Sleep 20s

Type "bin/instascript assets/demo/instascript-demo-reel.mp4"
Enter
Sleep 5s

Type "cat ~/ig_intel/Inbox/video-by-justxashton/transcript.txt"
Enter
Sleep 4s

Type "cat ~/ig_intel/Inbox/video-by-justxashton/source.json"
Enter
Sleep 4s

Type "echo '--- one command. local. verbatim + dedup built in. ---'"
Enter
Sleep 3s
