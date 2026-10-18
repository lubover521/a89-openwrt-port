import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1] / 'shared'
spec=importlib.util.spec_from_file_location('screen',HERE/'charge-screen.py')
screen=importlib.util.module_from_spec(spec);spec.loader.exec_module(screen)


class ChargeScreenTest(unittest.TestCase):
    def test_frames_track_charge_and_animation_with_both_languages(self):
        for language in ['zh','en']:
            art=screen.Artwork(HERE/'charge-art.zip',language)
            try:
                low=art.frame(15,'Charging',0)
                self.assertEqual(len(low),320*480*4)
                self.assertNotEqual(low,art.frame(15,'Charging',8))
                self.assertNotEqual(low,art.frame(97,'Charging',0))
                self.assertEqual(art.frame(100,'Full',0),art.frame(100,'Full',8))
                self.assertNotEqual(art.frame(100,'Full',0),art.frame(100,'Not charging',0))
            finally:art.close()

    def test_screen_sleeps_and_short_press_only_wakes_display(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);battery=root/'class/power_supply/battery';battery.mkdir(parents=True)
            (battery/'capacity').write_text('73');(battery/'status').write_text('Charging')
            bl=root/'brightness';bl.write_text('0')
            view=screen.Display.__new__(screen.Display)
            view.fd=9;view.tty=None;view.mode=None;view.backlights=[bl];view.lit=False
            view.until=0;view.next_frame=0;view.next_status=0;view.phase=0
            view.capacity=0;view.status='Unknown'
            view.art=screen.Artwork(HERE/'charge-art.zip')
            with patch.object(screen,'SYS',root), \
                    patch.object(screen.os,'pwrite',side_effect=lambda fd,data,offset:len(data)) as write, \
                    patch.object(screen.os,'close'):
                view.show(10);view.tick(10)
                self.assertEqual(bl.read_text().strip(),'150')
                self.assertEqual(view.capacity,73)
                view.tick(25)
                self.assertEqual(bl.read_text().strip(),'0')
                count=write.call_count;view.tick(30)
                self.assertEqual(write.call_count,count)
                view.show(35);view.tick(35)
                self.assertEqual(bl.read_text().strip(),'150')
                view.close()
                self.assertEqual(bl.read_text().strip(),'0')


if __name__=='__main__':unittest.main()
