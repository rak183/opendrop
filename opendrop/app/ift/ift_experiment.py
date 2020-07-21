# Copyright © 2020, Joseph Berry, Rico Tabor (opendrop.dev@gmail.com)
# OpenDrop is released under the GNU GPL License. You are free to
# modify and distribute the code, but always under the same license
# (i.e. you cannot make commercial derivatives).
#
# If you use this software in your research, please cite the following
# journal articles:
#
# J. D. Berry, M. J. Neeson, R. R. Dagastine, D. Y. C. Chan and
# R. F. Tabor, Measurement of surface and interfacial tension using
# pendant drop tensiometry. Journal of Colloid and Interface Science 454
# (2015) 226–237. https://doi.org/10.1016/j.jcis.2015.05.012
#
# E. Huang, T. Denning, A. Skoufis, J. Qi, R. R. Dagastine, R. F. Tabor
# and J. D. Berry, OpenDrop: Open-source software for pendant drop
# tensiometry & contact angle measurements, submitted to the Journal of
# Open Source Software
#
# These citations help us not only to understand who is using and
# developing OpenDrop, and for what purpose, but also to justify
# continued development of this code and other open source resources.
#
# OpenDrop is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.  You
# should have received a copy of the GNU General Public License along
# with this software.  If not, see <https://www.gnu.org/licenses/>.


from gi.repository import GObject, Gtk
from injector import inject

from opendrop.app.common.footer.linearnav import linear_navigator_footer_cs
from opendrop.app.common.footer.results import ResultsFooterStatus, results_footer_cs
from opendrop.appfw import ComponentFactory, Presenter, TemplateChild, component
from opendrop.utility.bindable import VariableBindable
from opendrop.widgets.yes_no_dialog import YesNoDialog

from .analysis_saver import ift_save_dialog_cs
from .services.progress import IFTAnalysisProgressHelper
from .services.session import IFTSession, IFTSessionModule


@component(
    template_path='./ift_experiment.ui',
    modules=[IFTSessionModule],
)
class IFTExperimentPresenter(Presenter[Gtk.Assistant]):
    action_area = TemplateChild('action_area')  # type: TemplateChild[Gtk.Stack]
    action0 = TemplateChild('action0')  # type: TemplateChild[Gtk.Container]
    action1 = TemplateChild('action1')  # type: TemplateChild[Gtk.Container]
    action2 = TemplateChild('action2')  # type: TemplateChild[Gtk.Container]
    action3 = TemplateChild('action3')  # type: TemplateChild[Gtk.Container]

    report_page = TemplateChild('report_page')

    @inject
    def __init__(
            self,
            cf: ComponentFactory,
            session: IFTSession,
            progress_helper: IFTAnalysisProgressHelper
    ) -> None:
        self.cf = cf
        self.session = session
        self.progress_helper = progress_helper

        session.bind_property('analyses', self.progress_helper, 'analyses', GObject.BindingFlags.SYNC_CREATE)

    def after_view_init(self) -> None:
        # Footer
        self.lin_footer_component = linear_navigator_footer_cs.factory(
            do_back=self.previous_page,
            do_next=self.next_page,
        ).create()
        self.lin_footer_component.view_rep.show()
        self.action0.add(self.lin_footer_component.view_rep)

        self._results_footer_status = VariableBindable(ResultsFooterStatus.IN_PROGRESS)
        self._results_footer_progress = VariableBindable(0.0)
        self._results_footer_time_elapsed = VariableBindable(0.0)
        self._results_footer_time_remaining = VariableBindable(0.0)
        self.results_footer_component = results_footer_cs.factory(
            in_status=self._results_footer_status,
            in_progress=self._results_footer_progress,
            in_time_elapsed=self._results_footer_time_elapsed,
            in_time_remaining=self._results_footer_time_remaining,
            do_back=self.previous_page,
            do_cancel=self.cancel_analyses,
            do_save=self.save_analyses,
        ).create()
        self.results_footer_component.view_rep.show()
        self.action3.add(self.results_footer_component.view_rep)

        self.session.bind_property('analyses', self.report_page, 'analyses', GObject.BindingFlags.SYNC_CREATE)

        self.progress_helper.connect('notify::status', self.progress_status_changed)
        self.progress_helper.connect('notify::fraction', self.progress_fraction_changed)
        self.progress_helper.connect('notify::time-start', self.progress_time_start_changed)
        self.progress_helper.connect('notify::est-complete', self.progress_est_complete_changed)

    def progress_status_changed(self, *_) -> None:
        status = self.progress_helper.status

        if status is IFTAnalysisProgressHelper.Status.ANALYSING:
            self._results_footer_status.set(ResultsFooterStatus.IN_PROGRESS)
        elif status is IFTAnalysisProgressHelper.Status.FINISHED:
            self._results_footer_status.set(ResultsFooterStatus.FINISHED)
        elif status is IFTAnalysisProgressHelper.Status.CANCELLED:
            self._results_footer_status.set(ResultsFooterStatus.CANCELLED)

    def progress_fraction_changed(self, *_) -> None:
        fraction = self.progress_helper.fraction
        self._results_footer_progress.set(fraction)

    def progress_time_start_changed(self, *_) -> None:
        self.update_times()

    def progress_est_complete_changed(self, *_) -> None:
        self.update_times()

    def update_times(self) -> None:
        self._results_footer_time_remaining.set(self.progress_helper.calculate_time_remaining())
        self._results_footer_time_elapsed.set(self.progress_helper.calculate_time_elapsed())

    def prepare(self, *_) -> None:
        # Update footer to show current page's action widgets.
        cur_page = self.host.get_current_page()
        if cur_page in (0, 1, 2):
            self.action_area.set_visible_child_name('0')
        else:
            self.action_area.set_visible_child_name(str(cur_page))

    def next_page(self) -> None:
        cur_page = self.host.get_current_page()
        if cur_page in (0, 1):
            self.host.next_page()
        elif cur_page == 2:
            self.start_analyses()
            self.host.next_page()
        else:
            # Ignore, on last page.
            return

    def previous_page(self) -> None:
        cur_page = self.host.get_current_page()
        if cur_page == 0:
            # Ignore, on first page.
            return
        elif cur_page in (1, 2):
            self.host.previous_page()
        elif cur_page == 3:
            self.clear_analyses()
            self.host.previous_page()

    def start_analyses(self) -> None:
        self.session.start_analyses()

    def clear_analyses(self) -> None:
        self.session.clear_analyses()

    def cancel_analyses(self) -> None:
        if hasattr(self, 'cancel_dialog'): return

        self.cancel_dialog = YesNoDialog(
            parent=self.host,
            message_format='Confirm cancel analysis?',
        )

        def hdl_response(dialog: Gtk.Widget, response: Gtk.ResponseType) -> None:
            del self.cancel_dialog
            dialog.destroy()

            self.progress_helper.disconnect(status_handler_id)

            if response == Gtk.ResponseType.YES:
                self.session.cancel_analyses()

        def hdl_progress_status(*_) -> None:
            if (self.progress_helper.status is IFTAnalysisProgressHelper.Status.FINISHED or
                    self.progress_helper.status is IFTAnalysisProgressHelper.Status.CANCELLED):
                self.cancel_dialog.close()

        # Close dialog if analysis finishes or cancels before user responds.
        status_handler_id = self.progress_helper.connect('notify::status', hdl_progress_status)

        self.cancel_dialog.connect('response', hdl_response)

        self.cancel_dialog.show()

    def save_analyses(self) -> None:
        if hasattr(self, 'save_dialog_component'): return

        save_options = self.session.create_save_options()

        def hdl_ok() -> None:
            self.save_dialog_component.destroy()
            del self.save_dialog_component
            self.session.save_analyses(save_options)

        def hdl_cancel() -> None:
            self.save_dialog_component.destroy()
            del self.save_dialog_component

        self.save_dialog_component = ift_save_dialog_cs.factory(
            parent_window=self.host,
            model=save_options,
            do_ok=hdl_ok,
            do_cancel=hdl_cancel,
        ).create()
        self.save_dialog_component.view_rep.show()

    def close(self, discard_unsaved: bool = False) -> None:
        if hasattr(self, 'confirm_discard_dialog'): return

        if discard_unsaved or self.session.safe_to_discard():
            self.session.quit()
            self.host.destroy()
        else:
            self.confirm_discard_dialog = YesNoDialog(
                message_format='Discard unsaved results?',
                parent=self.host,
            )

            def hdl_response(dialog: Gtk.Dialog, response: Gtk.ResponseType) -> None:
                del self.confirm_discard_dialog
                dialog.destroy()

                if response == Gtk.ResponseType.YES:
                    self.close(True)

            self.confirm_discard_dialog.connect('response', hdl_response)
            self.confirm_discard_dialog.show()

    def delete_event(self, *_) -> bool:
        self.close()
        return True

    def destroy(self, *_) -> None:
        self.lin_footer_component.destroy()
        self.results_footer_component.destroy()
